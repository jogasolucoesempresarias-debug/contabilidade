"""Pagamentos → planilha de importação do Alterdata, no formato EXATO do modelo dela
(`modelo+de+importacao+excel.xls`): .xls, aba Planilha1, cabeçalho na linha 1, 10 colunas.

A (lancto auto) e J (NrDocumento) são TEXTO para manter os zeros; D é data dd/mm/aaaa; E é
número com 2 casas, sempre positivo.
"""
import io

import xlwt

CABECALHO = ['lancto auto', 'debito', 'credito', 'data', 'valor', 'cód histórico',
             'complemento historico', 'Ccusto debito', 'Ccusto credito', 'NrDocumento']
# Larguras do modelo dela (1/256 de caractere). A data vai um pouco mais larga: com a fonte padrão
# do xlwt, 2960 mostrava "########" no Excel.
LARGURAS = [2960, 2960, 2960, 3400, 3195, 3084, 11069, 3303, 3449, 3266]


def linhas(pagamentos):
    """Só entra pagamento ok e com data. Ordem: data, depois descrição."""
    saida, n = [], 0
    for p in pagamentos:
        if p['situacao'] != 'ok' or p['data'] is None or not p.get('classificacao'):
            continue
        cl = p['classificacao']
        n += 1
        saida.append({
            'pagamento_id': p['id'],
            'lancto_auto': cl.get('lancto_auto') or '',
            'debito': cl.get('debito'), 'credito': cl.get('credito'),
            'data': p['data'], 'valor': p['valor'],
            'cod_historico': cl.get('cod_historico'),
            'complemento': cl.get('complemento') or p['descricao'],
            'ccusto_d': None, 'ccusto_c': None,
            'nr_documento': f'{n:05d}',
        })
    return saida


def gerar_xls(rows):
    wb = xlwt.Workbook(encoding='utf-8')
    ws = wb.add_sheet('Planilha1')
    texto = xlwt.easyxf(num_format_str='@')
    data = xlwt.easyxf(num_format_str='dd/mm/yyyy')
    valor = xlwt.easyxf(num_format_str='0.00')
    for c, nome in enumerate(CABECALHO):
        ws.write(0, c, nome)
    for i, r in enumerate(rows, start=1):
        ws.write(i, 0, r['lancto_auto'], texto)
        if r.get('debito') not in (None, ''):
            ws.write(i, 1, int(r['debito']))
        if r.get('credito') not in (None, ''):
            ws.write(i, 2, int(r['credito']))
        ws.write(i, 3, r['data'], data)
        ws.write(i, 4, float(r['valor']), valor)
        if r.get('cod_historico') not in (None, ''):
            ws.write(i, 5, int(r['cod_historico']))
        ws.write(i, 6, r['complemento'] or '')
        if r.get('ccusto_d') not in (None, ''):
            ws.write(i, 7, int(r['ccusto_d']))
        if r.get('ccusto_c') not in (None, ''):
            ws.write(i, 8, int(r['ccusto_c']))
        ws.write(i, 9, r['nr_documento'], texto)
    for c, largura in enumerate(LARGURAS):
        ws.col(c).width = largura
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
