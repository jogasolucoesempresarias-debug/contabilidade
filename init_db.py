"""Cria/migra o banco (idempotente). Rodar a cada deploy:
    docker exec <container> python -X utf8 init_db.py

Semeia: o admin inicial (ADMIN_EMAIL/ADMIN_SENHA, troca a senha no 1º acesso) e a regra do DAS
SEM código de lançamento automático — o código vem da tabela de lançamentos automáticos
do escritório (não se inventa código).
"""
import os

import psycopg2
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

load_dotenv()

DB = dict(host=os.getenv('DB_HOST', 'localhost'), port=os.getenv('DB_PORT', '5432'),
          user=os.getenv('DB_USER', 'postgres'), password=os.getenv('DB_PASSWORD', ''))
DB_NAME = os.getenv('DB_NAME', 'portal_contabil')

SCHEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id SERIAL PRIMARY KEY,
    nome TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    senha_hash TEXT NOT NULL,
    papel TEXT NOT NULL DEFAULT 'operador' CHECK (papel IN ('admin', 'operador')),
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    trocar_senha BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    ultimo_acesso TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS empresas (
    id SERIAL PRIMARY KEY,
    cnpj TEXT NOT NULL UNIQUE,                 -- só dígitos
    razao_social TEXT NOT NULL,
    ativa BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por INTEGER REFERENCES usuarios(id)
);

CREATE TABLE IF NOT EXISTS documentos (
    id SERIAL PRIMARY KEY,
    empresa_id INTEGER NOT NULL REFERENCES empresas(id),
    mes CHAR(7) NOT NULL,                      -- 'AAAA-MM' do lote em que foi enviado
    nome TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    tamanho INTEGER NOT NULL,
    formato TEXT NOT NULL,                     -- pdf | ofx | xml
    tipo TEXT,                                 -- DAS, Comprovante Sicoob, Extrato OFX…
    reconhecido BOOLEAN NOT NULL DEFAULT FALSE,
    origem TEXT,                               -- texto | ocr | ofx | xml
    confianca NUMERIC(4, 3),
    avisos JSONB NOT NULL DEFAULT '[]',
    resumo JSONB,
    motivo TEXT,                               -- por que não foi reconhecido
    texto TEXT,                                -- texto lido (para mapear documentos novos)
    situacao TEXT NOT NULL DEFAULT 'ativo' CHECK (situacao IN ('ativo', 'removido')),
    enviado_via TEXT NOT NULL DEFAULT 'escritorio',
    enviado_por INTEGER REFERENCES usuarios(id),
    enviado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    removido_por INTEGER REFERENCES usuarios(id),
    removido_em TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS documentos_sem_repeticao
    ON documentos (empresa_id, mes, sha256) WHERE situacao = 'ativo';
CREATE INDEX IF NOT EXISTS documentos_empresa_mes ON documentos (empresa_id, mes);

CREATE TABLE IF NOT EXISTS fatos (
    id SERIAL PRIMARY KEY,
    documento_id INTEGER NOT NULL REFERENCES documentos(id) ON DELETE CASCADE,
    ordem INTEGER NOT NULL,
    tipo TEXT NOT NULL,
    dados JSONB NOT NULL,
    barras44 TEXT,
    valor NUMERIC(14, 2),
    data_efetiva DATE,
    data_vencimento DATE
);
CREATE INDEX IF NOT EXISTS fatos_documento ON fatos (documento_id);

CREATE TABLE IF NOT EXISTS regras (
    id SERIAL PRIMARY KEY,
    empresa_id INTEGER REFERENCES empresas(id),   -- NULL = vale para todos
    gatilho TEXT NOT NULL CHECK (gatilho IN ('tipo_doc', 'historico_contem', 'cnpj')),
    valor TEXT NOT NULL,
    descricao TEXT,
    lancto_auto TEXT NOT NULL DEFAULT '',
    conta_debito INTEGER,
    conta_credito INTEGER,
    cod_historico INTEGER,
    modelo_complemento TEXT,
    ativa BOOLEAN NOT NULL DEFAULT TRUE,          -- regra se desliga, nunca se apaga
    criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS downloads (
    id SERIAL PRIMARY KEY,
    empresa_id INTEGER NOT NULL REFERENCES empresas(id),
    mes CHAR(7) NOT NULL,
    usuario_id INTEGER REFERENCES usuarios(id),
    usuario_nome TEXT,
    linhas INTEGER NOT NULL,
    baixado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS downloads_empresa_mes ON downloads (empresa_id, mes);
"""


def esperar_postgres(tentativas=30):
    """Na stack, o app pode subir antes do Postgres. Espera até ~60 s antes de desistir."""
    import time
    for i in range(tentativas):
        try:
            psycopg2.connect(dbname=DB_NAME, connect_timeout=3, **DB).close()
            return
        except psycopg2.OperationalError as e:
            if 'does not exist' in str(e):
                return                                   # servidor de pé; o banco é criado abaixo
            if i == tentativas - 1:
                raise
            print('aguardando o Postgres…')
            time.sleep(2)


def criar_banco_se_preciso():
    try:
        con = psycopg2.connect(dbname='postgres', **DB)
    except psycopg2.Error as e:
        print(f'(não conectou no banco "postgres" para checar {DB_NAME}: {e.__class__.__name__}) — seguindo')
        return
    con.autocommit = True
    with con.cursor() as cur:
        cur.execute('SELECT 1 FROM pg_database WHERE datname = %s', (DB_NAME,))
        if not cur.fetchone():
            cur.execute(f'CREATE DATABASE "{DB_NAME}"')
            print(f'banco {DB_NAME} criado')
    con.close()


def main():
    esperar_postgres()
    criar_banco_se_preciso()
    con = psycopg2.connect(dbname=DB_NAME, **DB)
    with con, con.cursor() as cur:
        cur.execute(SCHEMA)

        cur.execute('SELECT count(*) FROM usuarios')
        if cur.fetchone()[0] == 0:
            email = (os.getenv('ADMIN_EMAIL') or '').strip().lower()
            senha = os.getenv('ADMIN_SENHA') or ''
            if email and senha:
                cur.execute("INSERT INTO usuarios (nome, email, senha_hash, papel) VALUES (%s, %s, %s, 'admin')",
                            (os.getenv('ADMIN_NOME') or 'Administrador', email, generate_password_hash(senha)))
                print(f'admin inicial criado: {email} (troca a senha no 1º acesso)')
            else:
                print('nenhum usuário e ADMIN_EMAIL/ADMIN_SENHA vazios: crie com usuarios_cli.py')

        cur.execute("SELECT 1 FROM regras WHERE gatilho = 'tipo_doc' AND valor = 'DAS' AND empresa_id IS NULL")
        if not cur.fetchone():
            cur.execute("""INSERT INTO regras (gatilho, valor, descricao, lancto_auto, cod_historico, modelo_complemento)
                           VALUES ('tipo_doc', 'DAS', 'DAS (Simples Nacional)', '', NULL, 'DAS {competencia} Nº {numero}')""")
            print('regra do DAS semeada (sem código de lançamento automático)')
    con.close()
    print(f'init_db ok ({DB_NAME})')


if __name__ == '__main__':
    main()
