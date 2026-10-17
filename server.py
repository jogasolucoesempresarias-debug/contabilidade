"""Portal Contábil — área da contabilidade (fase 1 / demo).

Molde: JogaBarbearia (Flask + waitress + Postgres). Diferenças de propósito: sem CORS,
SECRET_KEY obrigatória em produção, limite de upload, arquivos servidos só com login.
Roteiro, decisões e especificação: PLANO.md e MAPEAMENTO.md do projeto (fora deste repositório,
que é público — nenhum dado de cliente entra aqui).
"""
import functools
import json
import logging
import os
import time
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, redirect, request, send_from_directory, session
from flask.json.provider import DefaultJSONProvider
from werkzeug.security import check_password_hash, generate_password_hash

import casamento
import planilha
from leitura import ArquivoRecusado, entrada, ler_arquivo
from leitura.util import cnpj_valido, fato_de_json, fato_para_json, formatar_cnpj, so_digitos

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('portal')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PAGINAS = os.path.join(BASE_DIR, 'paginas')
DOCS_DIR = os.getenv('DOCS_DIR') or os.path.join(BASE_DIR, '_dados', 'docs')
FUSO = ZoneInfo('America/Sao_Paulo')
PRODUCAO = os.getenv('FLASK_ENV') == 'production'
MAX_ARQUIVO = 15 * 1024 * 1024

AVISO_PADRAO = ('Demonstração: validado só DAS (PDF) e comprovante Sicoob. '
                'Outros documentos aparecem como “não reconhecido nesta versão”.')


class JSONProvider(DefaultJSONProvider):
    @staticmethod
    def default(o):
        if isinstance(o, Decimal):
            return str(o)
        if isinstance(o, (date, datetime)):
            return o.isoformat()
        return DefaultJSONProvider.default(o)


app = Flask(__name__, static_folder=None)
app.json = JSONProvider(app)
_secret = os.getenv('SECRET_KEY', '')
if PRODUCAO and len(_secret) < 32:
    raise SystemExit('SECRET_KEY obrigatória em produção (32+ caracteres).')
app.secret_key = _secret or 'dev-somente-local'
app.config.update(
    MAX_CONTENT_LENGTH=60 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=PRODUCAO,
    PERMANENT_SESSION_LIFETIME=12 * 3600,
)


# ── Banco ─────────────────────────────────────────────────────────────
def get_db():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'), port=os.getenv('DB_PORT', '5432'),
        dbname=os.getenv('DB_NAME', 'portal_contabil'),
        user=os.getenv('DB_USER', 'postgres'), password=os.getenv('DB_PASSWORD', ''),
        options='-c timezone=America/Sao_Paulo')


def q_all(sql, params=None):
    with get_db() as con, con.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params or ())
        return [dict(r) for r in cur.fetchall()]


def q_one(sql, params=None):
    rows = q_all(sql, params)
    return rows[0] if rows else None


def execute(sql, params=None, returning=False):
    con = get_db()
    try:
        with con, con.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params or ())
            return dict(cur.fetchone()) if returning else None
    finally:
        con.close()


# ── Login ─────────────────────────────────────────────────────────────
_RATE = {}


def rate_limit_ok(chave, maximo=8, janela_seg=600):
    agora = time.time()
    hist = [t for t in _RATE.get(chave, []) if agora - t < janela_seg]
    _RATE[chave] = hist
    if len(hist) >= maximo:
        return False
    hist.append(agora)
    return True


def ip_cliente():
    return (request.headers.get('X-Forwarded-For') or request.remote_addr or '').split(',')[0].strip()


def login_required(f):
    @functools.wraps(f)
    def dec(*a, **k):
        if 'user_id' not in session:
            if request.path.startswith('/api/'):
                return jsonify({'ok': False, 'error': 'Sua sessão expirou. Entre de novo.'}), 401
            return redirect('/login')
        if session.get('trocar_senha') and request.path not in ('/trocar-senha', '/api/trocar-senha', '/api/me'):
            if request.path.startswith('/api/'):
                return jsonify({'ok': False, 'error': 'Troque a senha para continuar', 'redirect': '/trocar-senha'}), 403
            return redirect('/trocar-senha')
        return f(*a, **k)
    return dec


def pagina(nome):
    return send_from_directory(PAGINAS, nome)


@app.route('/static/<path:arquivo>')
def static_assets(arquivo):
    return send_from_directory(os.path.join(BASE_DIR, 'static'), arquivo)


@app.route('/health')
def health():
    return jsonify({'ok': True, 'service': 'portal-contabil'})


@app.route('/login')
def login_page():
    return redirect('/') if 'user_id' in session and not session.get('trocar_senha') else pagina('login.html')


@app.route('/trocar-senha')
@login_required
def trocar_senha_page():
    return pagina('trocar-senha.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


@app.route('/api/login', methods=['POST'])
def api_login():
    if not rate_limit_ok('login:' + ip_cliente()):
        return jsonify({'ok': False, 'error': 'Muitas tentativas. Espere alguns minutos e tente de novo.'}), 429
    d = request.get_json(silent=True) or {}
    email = (d.get('email') or '').strip().lower()
    senha = d.get('senha') or ''
    sup_email = os.getenv('SUPORTE_EMAIL', '').strip().lower()
    sup_senha = os.getenv('SUPORTE_SENHA', '')
    session.clear()
    session.permanent = True
    if sup_email and sup_senha and email == sup_email and senha == sup_senha:
        session.update(user_id=0, nome='Suporte JOGA', papel='admin', trocar_senha=False)
        return jsonify({'ok': True, 'redirect': '/'})
    u = q_one('SELECT * FROM usuarios WHERE email = %s AND ativo', (email,))
    if not u or not check_password_hash(u['senha_hash'], senha):
        return jsonify({'ok': False, 'error': 'E-mail ou senha incorretos.'}), 401
    execute('UPDATE usuarios SET ultimo_acesso = now() WHERE id = %s', (u['id'],))
    session.update(user_id=u['id'], nome=u['nome'], papel=u['papel'], trocar_senha=u['trocar_senha'])
    return jsonify({'ok': True, 'redirect': '/trocar-senha' if u['trocar_senha'] else '/'})


@app.route('/api/trocar-senha', methods=['POST'])
@login_required
def api_trocar_senha():
    d = request.get_json(silent=True) or {}
    nova = d.get('nova') or ''
    if len(nova) < 8:
        return jsonify({'ok': False, 'error': 'A senha precisa ter pelo menos 8 caracteres.'}), 400
    if session.get('user_id') == 0:
        return jsonify({'ok': False, 'error': 'O acesso de suporte não troca senha.'}), 400
    u = q_one('SELECT senha_hash FROM usuarios WHERE id = %s', (session['user_id'],))
    if not session.get('trocar_senha') and not check_password_hash(u['senha_hash'], d.get('atual') or ''):
        return jsonify({'ok': False, 'error': 'A senha atual não confere.'}), 400
    execute('UPDATE usuarios SET senha_hash = %s, trocar_senha = FALSE WHERE id = %s',
            (generate_password_hash(nova), session['user_id']))
    session['trocar_senha'] = False
    return jsonify({'ok': True, 'redirect': '/'})


@app.route('/api/me')
@login_required
def api_me():
    return jsonify({'ok': True, 'nome': session.get('nome'), 'papel': session.get('papel'),
                    'trocar_senha': session.get('trocar_senha', False)})


@app.route('/api/marca')
def api_marca():
    aviso = os.getenv('AVISO_DEMO')
    return jsonify({'nome': os.getenv('ESCRITORIO_NOME', 'Portal Contábil'),
                    'aviso': AVISO_PADRAO if aviso is None else aviso,
                    'hoje': datetime.now(FUSO).date()})


@app.route('/marca.css')
def marca_css():
    cor = os.getenv('ESCRITORIO_COR', '').strip()
    css = f':root{{--marca:{cor};}}' if cor.startswith('#') and len(cor) in (4, 7) else ''
    return Response(css, mimetype='text/css')


# ── Páginas ───────────────────────────────────────────────────────────
@app.route('/')
@login_required
def inicio():
    return redirect('/clientes')


@app.route('/clientes')
@login_required
def clientes_page():
    return pagina('clientes.html')


@app.route('/cliente/<int:empresa_id>/<mes>')
@login_required
def cliente_page(empresa_id, mes):
    return pagina('cliente.html')


@app.route('/cliente/<int:empresa_id>/<mes>/enviar')
@login_required
def enviar_page(empresa_id, mes):
    return pagina('enviar.html')


@app.route('/regras')
@login_required
def regras_page():
    return pagina('regras.html')


# ── Mês do cliente: documentos → pagamentos → planilha ───────────────
def mes_valido(mes):
    try:
        datetime.strptime(mes, '%Y-%m')
        return True
    except (TypeError, ValueError):
        return False


def carregar_docs(empresa_id, mes):
    docs = q_all("""SELECT d.id, d.nome, d.tipo, d.formato, d.reconhecido, d.origem, d.confianca, d.avisos,
                           d.motivo, d.resumo, d.tamanho, d.enviado_via, d.enviado_em, u.nome AS enviado_por
                    FROM documentos d LEFT JOIN usuarios u ON u.id = d.enviado_por
                    WHERE d.empresa_id = %s AND d.mes = %s AND d.situacao = 'ativo' ORDER BY d.enviado_em, d.id""",
                 (empresa_id, mes))
    if docs:
        fatos = q_all('SELECT documento_id, dados FROM fatos WHERE documento_id = ANY(%s) ORDER BY documento_id, ordem',
                      ([d['id'] for d in docs],))
        por_doc = {}
        for f in fatos:
            por_doc.setdefault(f['documento_id'], []).append(fato_de_json(f['dados']))
        for d in docs:
            d['fatos'] = por_doc.get(d['id'], [])
            d['confianca'] = float(d['confianca']) if d['confianca'] is not None else None
    return docs


def regras_ativas():
    return q_all('SELECT * FROM regras WHERE ativa ORDER BY id')


def visao_mes(empresa, mes):
    docs = carregar_docs(empresa['id'], mes)
    res = casamento.calcular(docs, empresa, regras_ativas())
    linhas = planilha.linhas(res['pagamentos'])
    ultimo_download = q_one('SELECT usuario_nome, baixado_em, linhas FROM downloads WHERE empresa_id = %s AND mes = %s '
                            'ORDER BY baixado_em DESC LIMIT 1', (empresa['id'], mes))
    ultimo_envio = max((d['enviado_em'] for d in docs), default=None)
    usados = {}
    for p in res['pagamentos']:
        for i in p['doc_ids']:
            usados.setdefault(i, []).append(p['id'])
    pend_por_doc = {}
    for pe in res['pendencias']:
        for i in pe['doc_ids']:
            pend_por_doc.setdefault(i, []).append(pe['codigo'])
    for d in docs:
        d['pagamentos'] = usados.get(d['id'], [])
        d['pendencias'] = pend_por_doc.get(d['id'], [])
        d['fatos'] = [fato_para_json(f) for f in d['fatos']]
    reais = [p for p in res['pendencias'] if not p['informativa']]
    # Pendência aberta vem antes de "Baixada": baixar a planilha não resolve o que ficou de fora.
    if not docs:
        situacao = 'sem_envio'
    elif reais:
        situacao = 'pendencia'
    elif ultimo_download and ultimo_envio and ultimo_download['baixado_em'] >= ultimo_envio:
        situacao = 'baixada'
    elif linhas:
        situacao = 'pronta'
    else:
        situacao = 'recebendo'
    return {'empresa': {**empresa, 'cnpj_fmt': formatar_cnpj(empresa['cnpj'])}, 'mes': mes,
            'situacao': situacao, 'documentos': docs, 'pagamentos': res['pagamentos'],
            'pendencias': res['pendencias'], 'pendencias_abertas': len(reais), 'linhas': linhas,
            'ultimo_download': ultimo_download}


def empresa_ou_404(empresa_id):
    return q_one('SELECT id, cnpj, razao_social, ativa FROM empresas WHERE id = %s', (empresa_id,))


@app.route('/api/clientes')
@login_required
def api_clientes():
    mes = request.args.get('mes') or datetime.now(FUSO).strftime('%Y-%m')
    if not mes_valido(mes):
        return jsonify({'ok': False, 'error': 'Mês inválido.'}), 400
    saida = []
    for e in q_all('SELECT id, cnpj, razao_social, ativa FROM empresas WHERE ativa ORDER BY razao_social'):
        v = visao_mes(e, mes)
        saida.append({'id': e['id'], 'razao_social': e['razao_social'], 'cnpj': formatar_cnpj(e['cnpj']),
                      'documentos': len(v['documentos']), 'pagamentos': len(v['pagamentos']),
                      'linhas': len(v['linhas']), 'pendencias': v['pendencias_abertas'],
                      'situacao': v['situacao'], 'ultimo_download': v['ultimo_download']})
    return jsonify({'ok': True, 'mes': mes, 'clientes': saida})


@app.route('/api/clientes', methods=['POST'])
@login_required
def api_criar_cliente():
    d = request.get_json(silent=True) or {}
    cnpj = so_digitos(d.get('cnpj'))
    razao = (d.get('razao_social') or '').strip()
    if not cnpj_valido(cnpj):
        return jsonify({'ok': False, 'error': 'CNPJ inválido. Confira os números.'}), 400
    if len(razao) < 2:
        return jsonify({'ok': False, 'error': 'Informe a razão social.'}), 400
    if q_one('SELECT 1 FROM empresas WHERE cnpj = %s', (cnpj,)):
        return jsonify({'ok': False, 'error': 'Já existe um cliente com este CNPJ.'}), 409
    novo = execute('INSERT INTO empresas (cnpj, razao_social, criado_por) VALUES (%s, %s, %s) RETURNING id',
                   (cnpj, razao.upper(), session.get('user_id') or None), returning=True)
    return jsonify({'ok': True, 'id': novo['id']})


@app.route('/api/cliente/<int:empresa_id>/<mes>')
@login_required
def api_cliente_mes(empresa_id, mes):
    e = empresa_ou_404(empresa_id)
    if not e or not mes_valido(mes):
        return jsonify({'ok': False, 'error': 'Cliente ou mês não encontrado.'}), 404
    return jsonify({'ok': True, **visao_mes(e, mes)})


def caminho_arquivo(sha):
    return os.path.join(DOCS_DIR, sha[:2], sha)


@app.route('/api/cliente/<int:empresa_id>/<mes>/documentos', methods=['POST'])
@login_required
def api_enviar(empresa_id, mes):
    e = empresa_ou_404(empresa_id)
    if not e or not mes_valido(mes):
        return jsonify({'ok': False, 'error': 'Cliente ou mês não encontrado.'}), 404
    via = 'cliente' if request.form.get('via') == 'cliente' else 'escritorio'
    resultados = []
    for arq in request.files.getlist('arquivos'):
        nome = os.path.basename(arq.filename or 'arquivo')[:200]
        conteudo = arq.read()
        if len(conteudo) > MAX_ARQUIVO:
            resultados.append({'nome': nome, 'ok': False, 'erro': 'Arquivo maior que 15 MB.'})
            continue
        try:
            formato = entrada.identificar(conteudo)
        except ArquivoRecusado as ex:
            resultados.append({'nome': nome, 'ok': False, 'erro': str(ex)})
            continue
        sha = entrada.sha256(conteudo)
        if q_one("SELECT 1 FROM documentos WHERE empresa_id = %s AND mes = %s AND sha256 = %s AND situacao = 'ativo'",
                 (empresa_id, mes, sha)):
            resultados.append({'nome': nome, 'ok': False, 'erro': 'Este arquivo já foi enviado neste mês.'})
            continue
        try:
            lido = ler_arquivo(conteudo)
            motivo = None if lido['reconhecido'] else (lido['avisos'][0] if lido['avisos'] else 'tipo de documento ainda não mapeado')
        except Exception:
            log.exception('erro lendo %s', nome)
            lido = {'formato': formato, 'tipo': None, 'reconhecido': False, 'origem': None, 'confianca': None,
                    'fatos': [], 'avisos': ['Não foi possível ler o arquivo'], 'texto': '', 'resumo': None}
            motivo = 'erro ao ler o arquivo'
        os.makedirs(os.path.dirname(caminho_arquivo(sha)), exist_ok=True)
        if not os.path.exists(caminho_arquivo(sha)):
            with open(caminho_arquivo(sha), 'wb') as fh:
                fh.write(conteudo)
        con = get_db()
        try:
            with con, con.cursor() as cur:
                cur.execute("""INSERT INTO documentos (empresa_id, mes, nome, sha256, tamanho, formato, tipo, reconhecido,
                                   origem, confianca, avisos, resumo, motivo, texto, enviado_via, enviado_por)
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                            (empresa_id, mes, nome, sha, len(conteudo), lido['formato'], lido['tipo'], lido['reconhecido'],
                             lido['origem'], lido['confianca'], json.dumps(lido['avisos'], ensure_ascii=False),
                             json.dumps(lido['resumo'], ensure_ascii=False) if lido['resumo'] else None, motivo,
                             (lido['texto'] or '')[:100000], via, session.get('user_id') or None))
                doc_id = cur.fetchone()[0]
                for i, f in enumerate(lido['fatos']):
                    j = fato_para_json({k: v for k, v in f.items() if k != 'avisos'})
                    cur.execute("""INSERT INTO fatos (documento_id, ordem, tipo, dados, barras44, valor, data_efetiva, data_vencimento)
                                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                                (doc_id, i, f['tipo'], json.dumps(j, ensure_ascii=False), f.get('barras44'),
                                 f.get('valor_total'), f.get('data_efetiva'), f.get('data_vencimento')))
        finally:
            con.close()
        resultados.append({'nome': nome, 'ok': True, 'id': doc_id, 'tipo': lido['tipo'] or 'Não reconhecido nesta versão',
                           'reconhecido': lido['reconhecido'], 'avisos': lido['avisos']})
        log.info('documento %s (%s) empresa=%s mes=%s via=%s tipo=%s', doc_id, nome, empresa_id, mes, via, lido['tipo'])
    if not resultados:
        return jsonify({'ok': False, 'error': 'Nenhum arquivo recebido.'}), 400
    return jsonify({'ok': True, 'resultados': resultados})


@app.route('/api/documento/<int:doc_id>/arquivo')
@login_required
def api_arquivo(doc_id):
    d = q_one("SELECT sha256, formato, nome FROM documentos WHERE id = %s", (doc_id,))
    if not d or not os.path.exists(caminho_arquivo(d['sha256'])):
        return jsonify({'ok': False, 'error': 'Arquivo não encontrado.'}), 404
    tipos = {'pdf': 'application/pdf', 'ofx': 'text/plain; charset=utf-8', 'xml': 'text/plain; charset=utf-8'}
    with open(caminho_arquivo(d['sha256']), 'rb') as fh:
        conteudo = fh.read()
    resp = Response(conteudo, mimetype=tipos.get(d['formato'], 'application/octet-stream'))
    resp.headers['Content-Disposition'] = 'inline'
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['Cache-Control'] = 'private, max-age=300'
    return resp


@app.route('/api/documento/<int:doc_id>', methods=['DELETE'])
@login_required
def api_remover(doc_id):
    d = q_one("SELECT id FROM documentos WHERE id = %s AND situacao = 'ativo'", (doc_id,))
    if not d:
        return jsonify({'ok': False, 'error': 'Documento não encontrado.'}), 404
    execute("UPDATE documentos SET situacao = 'removido', removido_por = %s, removido_em = now() WHERE id = %s",
            (session.get('user_id') or None, doc_id))
    return jsonify({'ok': True})


@app.route('/api/cliente/<int:empresa_id>/<mes>/planilha.xls')
@login_required
def api_planilha(empresa_id, mes):
    e = empresa_ou_404(empresa_id)
    if not e or not mes_valido(mes):
        return jsonify({'ok': False, 'error': 'Cliente ou mês não encontrado.'}), 404
    v = visao_mes(e, mes)
    if not v['linhas']:
        return jsonify({'ok': False, 'error': 'Ainda não há lançamentos prontos neste mês.'}), 400
    conteudo = planilha.gerar_xls(v['linhas'])
    execute('INSERT INTO downloads (empresa_id, mes, usuario_id, usuario_nome, linhas) VALUES (%s,%s,%s,%s,%s)',
            (empresa_id, mes, session.get('user_id') or None, session.get('nome'), len(v['linhas'])))
    nome = f'lancamentos_{e["cnpj"]}_{mes}.xls'
    return Response(conteudo, mimetype='application/vnd.ms-excel',
                    headers={'Content-Disposition': f'attachment; filename="{nome}"'})


@app.route('/api/regras')
@login_required
def api_regras():
    regras = q_all("""SELECT r.*, e.razao_social AS empresa FROM regras r LEFT JOIN empresas e ON e.id = r.empresa_id
                      ORDER BY r.ativa DESC, r.empresa_id NULLS FIRST, r.id""")
    return jsonify({'ok': True, 'regras': regras})


@app.errorhandler(413)
def muito_grande(_):
    return jsonify({'ok': False, 'error': 'Envio grande demais. Mande no máximo 60 MB por vez.'}), 413


if __name__ == '__main__':
    porta = int(os.getenv('PORT', '5000'))
    if PRODUCAO or os.getenv('USAR_WAITRESS') == '1':
        from waitress import serve
        log.info('Portal Contábil em :%s (waitress)', porta)
        serve(app, host='0.0.0.0', port=porta, threads=8)
    else:
        app.run(host='127.0.0.1', port=porta, debug=True)
