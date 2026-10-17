"""Usuários da equipe do escritório (a tela de equipe fica para depois).

    python -X utf8 usuarios_cli.py criar ana@escritorio.com.br "Ana Paula" operador
    python -X utf8 usuarios_cli.py senha ana@escritorio.com.br        # nova senha provisória
    python -X utf8 usuarios_cli.py listar

A senha provisória aparece uma vez na tela; a pessoa troca no 1º acesso.
"""
import secrets
import sys

from werkzeug.security import generate_password_hash

from server import execute, q_all, q_one


def senha_provisoria():
    return secrets.token_urlsafe(9)


def main(args):
    if not args or args[0] not in ('criar', 'senha', 'listar'):
        print(__doc__)
        return 1
    if args[0] == 'listar':
        for u in q_all('SELECT email, nome, papel, ativo, ultimo_acesso FROM usuarios ORDER BY nome'):
            print(f"{u['email']:<40} {u['nome']:<25} {u['papel']:<9} {'ativo' if u['ativo'] else 'inativo'} {u['ultimo_acesso'] or ''}")
        return 0
    email = args[1].strip().lower()
    senha = senha_provisoria()
    if args[0] == 'criar':
        nome = args[2] if len(args) > 2 else email.split('@')[0]
        papel = args[3] if len(args) > 3 else 'operador'
        if q_one('SELECT 1 FROM usuarios WHERE email = %s', (email,)):
            print('já existe; use "senha" para gerar outra senha provisória')
            return 1
        execute('INSERT INTO usuarios (nome, email, senha_hash, papel) VALUES (%s, %s, %s, %s)',
                (nome, email, generate_password_hash(senha), papel))
    else:
        if not q_one('SELECT 1 FROM usuarios WHERE email = %s', (email,)):
            print('usuário não encontrado')
            return 1
        execute('UPDATE usuarios SET senha_hash = %s, trocar_senha = TRUE WHERE email = %s',
                (generate_password_hash(senha), email))
    print(f'{email}  senha provisória: {senha}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
