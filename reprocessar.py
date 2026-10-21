"""Relê os documentos já enviados com os leitores ATUAIS (a leitura fica gravada no envio; quando
um leitor melhora, os documentos antigos só mudam depois de reprocessados).

    python -X utf8 reprocessar.py               # todos os documentos ativos
    python -X utf8 reprocessar.py 12 15         # só esses ids

No servidor:
    docker exec $(docker ps -q -f name=contabilidade_contabilidade-app) python -X utf8 reprocessar.py

Cada documento é regravado numa transação própria: se um falhar, os outros seguem.
"""
import json
import os
import sys

from leitura import ler_arquivo
from server import caminho_arquivo, get_db, gravar_fatos, q_all


def reprocessar(ids=None):
    filtro, params = ("AND id = ANY(%s)", (list(ids),)) if ids else ("", ())
    docs = q_all(f"SELECT id, nome, sha256, tipo FROM documentos WHERE situacao = 'ativo' {filtro} ORDER BY id", params)
    mudou = 0
    for d in docs:
        caminho = caminho_arquivo(d['sha256'])
        if not os.path.exists(caminho):
            print(f"{d['id']:>5}  {d['nome']}: arquivo não encontrado, pulado")
            continue
        try:
            lido = ler_arquivo(open(caminho, 'rb').read())
        except Exception as e:                               # noqa: BLE001 — um arquivo ruim não para o lote
            print(f"{d['id']:>5}  {d['nome']}: erro ao ler ({e.__class__.__name__}), mantido como estava")
            continue
        motivo = None if lido['reconhecido'] else (lido['avisos'][0] if lido['avisos'] else 'tipo de documento ainda não mapeado')
        con = get_db()
        try:
            with con, con.cursor() as cur:
                cur.execute("""UPDATE documentos SET tipo = %s, reconhecido = %s, origem = %s, confianca = %s, avisos = %s,
                                      resumo = %s, motivo = %s, texto = %s WHERE id = %s""",
                            (lido['tipo'], lido['reconhecido'], lido['origem'], lido['confianca'],
                             json.dumps(lido['avisos'], ensure_ascii=False),
                             json.dumps(lido['resumo'], ensure_ascii=False) if lido['resumo'] else None,
                             motivo, (lido['texto'] or '')[:100000], d['id']))
                cur.execute('DELETE FROM fatos WHERE documento_id = %s', (d['id'],))
                gravar_fatos(cur, d['id'], lido['fatos'])
        finally:
            con.close()
        mudou += 1
        print(f"{d['id']:>5}  {d['nome']}: {lido['tipo'] or 'não reconhecido'} ({len(lido['fatos'])} fato(s))")
    print(f'{mudou} de {len(docs)} documento(s) reprocessado(s)')


if __name__ == '__main__':
    reprocessar([int(x) for x in sys.argv[1:]] or None)
