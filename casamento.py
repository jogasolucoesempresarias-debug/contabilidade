"""Fatos lidos → pagamentos + pendências (MAPEAMENTO §5, §6 e §9).

Regra dela: vários documentos do mesmo pagamento = UMA linha; a data é a do extrato ou do
comprovante, nunca o vencimento. Tudo aqui é determinístico: é recalculado a cada envio.
"""
from datetime import timedelta
from decimal import Decimal

from classificacao import classificar
from leitura.util import brl, normalizar_nome, so_digitos

ZERO = Decimal('0.00')
CONFIANCA_MINIMA_OCR = 0.80

PENDENCIAS = {
    'P1': 'Linha do extrato sem documento e sem regra',
    'P2': 'Guia ou boleto sem débito no extrato',
    'P3': 'Falta o extrato para confirmar a data',
    'P4': 'Pagamento de conta sem extrato',
    'P5': 'Mais de um débito possível no extrato',
    'P6': 'Documento de outra empresa',
    'P7': 'Documento repetido',
    'P9': 'Valor pago diferente do documento',
    'P10': 'Leitura com baixa confiança',
    'NR': 'Documento não reconhecido nesta versão',
    'SR': 'Documento sem regra de classificação',
    'CL': 'Falta o código do lançamento automático',
    'JM': 'Pagamento com juros ou multa',
    'DV': 'Data pelo vencimento da guia',
}
# Pendências que só informam: o pagamento continua indo para a planilha.
INFORMATIVAS = {'P4', 'P7', 'JM', 'DV'}


def _pend(codigo, detalhe, doc_ids=(), pagamento_id=None):
    return {'codigo': codigo, 'titulo': PENDENCIAS[codigo], 'detalhe': detalhe,
            'doc_ids': list(doc_ids), 'pagamento_id': pagamento_id,
            'informativa': codigo in INFORMATIVAS}


def _janela(grupo):
    """Intervalo de datas em que o débito do extrato é aceito para este grupo."""
    c, g = grupo.get('comprovante'), grupo.get('guia')
    if c and c.get('data_efetiva'):
        d = c['data_efetiva']
        return d, d + timedelta(days=3)                       # extrato pode lançar em D+1..D+3
    if g and g.get('data_vencimento'):
        v = g['data_vencimento']
        return v - timedelta(days=45), v + timedelta(days=30)  # pago antes ou com atraso
    if c and (c.get('data_agendada') or c.get('data_geracao')):
        d = c.get('data_agendada') or c['data_geracao']
        return d - timedelta(days=35), d + timedelta(days=35)
    return None, None


def _mesma_conta(c, e):
    if not c or not c.get('conta') or not e.get('conta'):
        return True
    a, b = so_digitos(c['conta']), so_digitos(e['conta'])
    return bool(a) and bool(b) and (b.endswith(a) or a.endswith(b))


def _pontos_nome(grupo, e):
    """Desempate K6: palavras em comum entre o histórico do extrato e quem recebeu."""
    hist = set(normalizar_nome(e.get('historico')))
    c, g = grupo.get('comprovante') or {}, grupo.get('guia') or {}
    alvo = set(normalizar_nome(' '.join(filter(None, [g.get('contraparte_nome'), g.get('subtipo'),
                                                     c.get('convenio'), c.get('descricao')]))))
    if 'DAS' in alvo or 'SIMPLES' in alvo:
        alvo |= {'DAS', 'SIMPLES', 'NACIONAL', 'RECEITA', 'FEDERAL', 'CONV', 'CONVENIO'}
    return len(hist & alvo)


def calcular(docs, empresa, regras):
    """docs: [{id, nome, reconhecido, origem, confianca, fatos}] já lidos. empresa: {id, cnpj}."""
    pend, fatos = [], []
    cnpj_empresa = so_digitos(empresa.get('cnpj'))

    for d in docs:
        if not d.get('reconhecido'):
            pend.append(_pend('NR', f'{d["nome"]}: {d.get("motivo") or "tipo de documento ainda não mapeado"}', [d['id']]))
        if d.get('origem') == 'ocr' and (d.get('confianca') or 0) < CONFIANCA_MINIMA_OCR:
            pend.append(_pend('P10', f'{d["nome"]}: confiança {(d.get("confianca") or 0):.0%}', [d['id']]))
        for i, f in enumerate(d.get('fatos') or []):
            fatos.append({**f, 'doc_id': d['id'], 'doc_nome': d['nome'], '_ref': f'{d["id"]}:{i}'})

    # Documento de outra empresa (guia com CNPJ do contribuinte diferente do cliente).
    validos = []
    for f in fatos:
        cnpj_doc = so_digitos(f.get('cnpj_documento'))
        if cnpj_doc and cnpj_empresa and cnpj_doc != cnpj_empresa:
            pend.append(_pend('P6', f'{f["doc_nome"]}: CNPJ {f.get("cnpj_documento")} não é desta empresa', [f['doc_id']]))
            continue
        validos.append(f)

    # Repetidos: mesmo código de barras em dois arquivos do mesmo tipo; mesma transação de extrato.
    vistos_barras, vistos_fitid, unicos = {}, set(), []
    for f in validos:
        if f['tipo'] == 'extrato_linha':
            chave = (f.get('conta'), f.get('fitid')) if f.get('fitid') else \
                    (f.get('conta'), f['data_efetiva'], f['valor_total'], f.get('historico'))
            if chave in vistos_fitid:
                continue                                   # extratos com período sobreposto
            vistos_fitid.add(chave)
        elif f.get('barras44'):
            chave = (f['tipo'], f['barras44'])
            if chave in vistos_barras:
                pend.append(_pend('P7', f'{f["doc_nome"]} repete {vistos_barras[chave]}', [f['doc_id']]))
                continue
            vistos_barras[chave] = f['doc_nome']
        unicos.append(f)

    extrato = [f for f in unicos if f['tipo'] == 'extrato_linha']
    comprovantes = [f for f in unicos if f['tipo'] == 'comprovante']
    guias = [f for f in unicos if f['tipo'] in ('guia', 'boleto')]

    # K1: comprovante ↔ guia/boleto pelo código de barras.
    grupos, guias_usadas = [], set()
    for c in comprovantes:
        g = next((x for x in guias if x['_ref'] not in guias_usadas and c.get('barras44')
                  and x.get('barras44') == c['barras44']), None)
        if g:
            guias_usadas.add(g['_ref'])
        grupos.append({'comprovante': c, 'guia': g, 'chave': 'Código de barras' if g else None})
    for g in guias:
        if g['_ref'] not in guias_usadas:
            grupos.append({'comprovante': None, 'guia': g, 'chave': None})

    # K4/K5 + K6: cada grupo procura o seu débito no extrato.
    livres = [e for e in extrato if e['sentido'] == 'saida']
    for gr in grupos:
        c, g = gr['comprovante'], gr['guia']
        valor = (c or g)['valor_total']
        ini, fim = _janela(gr)
        cands = [e for e in livres if e['valor_total'] == valor and _mesma_conta(c, e)
                 and (ini is None or ini <= e['data_efetiva'] <= fim)]
        if len(cands) > 1:
            pontos = {e['_ref']: _pontos_nome(gr, e) for e in cands}
            melhor = max(pontos.values())
            if melhor > 0 and list(pontos.values()).count(melhor) == 1:
                cands = [e for e in cands if pontos[e['_ref']] == melhor]
        if len(cands) == 1:
            gr['extrato'] = cands[0]
            livres.remove(cands[0])
            gr['chave'] = (gr['chave'] + ' + valor e data') if gr['chave'] else 'Valor e data'
        elif len(cands) > 1:
            gr['ambiguo'] = cands

    pagamentos = []
    for gr in grupos:
        pagamentos.append(_pagamento_de_grupo(gr, pend))
    casados = {gr['extrato']['_ref'] for gr in grupos if gr.get('extrato')}
    for e in extrato:
        if e['_ref'] not in casados:
            pagamentos.append(_pagamento_de_extrato(e))

    for p in pagamentos:
        cl = classificar(p, regras, empresa.get('id'))
        p['classificacao'] = cl
        if p['situacao'] != 'ok':
            continue
        if not cl:
            p['situacao'] = 'pendente'
            pend.append(_pend('P1' if p['origem'] == 'extrato' else 'SR',
                              f'{p["descricao"]} ({brl(p["valor"])}): nenhuma regra de classificação',
                              p['doc_ids'], p['id']))
        elif not cl['lancto_auto'] and not (cl.get('debito') and cl.get('credito')):
            pend.append(_pend('CL', f'{p["descricao"]}: a regra "{cl["regra"]}" ainda não tem o código '
                                    'do lançamento automático (pedido ao escritório)', p['doc_ids'], p['id']))

    for p in pagamentos:
        for k in ('_guia', '_comprovante', '_extrato'):
            p.pop(k, None)
    pagamentos.sort(key=lambda p: (p['data'] is None, p['data'] or 0, p['descricao']))
    return {'pagamentos': pagamentos, 'pendencias': pend}


def _pagamento_de_grupo(gr, pend):
    c, g, e = gr['comprovante'], gr['guia'], gr.get('extrato')
    base = c or g
    docs = [x for x in (e, c, g) if x]
    pid = 'B:' + base['barras44'] if base.get('barras44') else 'D:' + base['_ref']
    descricao = (g or {}).get('rotulo') or (c or {}).get('descricao') or base.get('rotulo')
    if g and g.get('subtipo') == 'DAS':
        descricao = f'DAS {g.get("competencia") or ""}'.strip()
    # Data: extrato › comprovante › vencimento da guia. O vencimento só entra quando há
    # comprovante de PAGAMENTO sem data (segunda via do Sicoob: "Pagamento efetuado null") —
    # decisão de 17/10. Agendamento continua sem data até o extrato.
    if e:
        data, fonte = e['data_efetiva'], 'extrato'
    elif c and c.get('data_efetiva'):
        data, fonte = c['data_efetiva'], 'comprovante'
    elif c and not c.get('agendamento') and g and g.get('data_vencimento'):
        data, fonte = g['data_vencimento'], 'vencimento'
    else:
        data, fonte = None, None
    p = {
        'id': pid, 'origem': 'documentos', 'situacao': 'ok', 'data': data, 'fonte_data': fonte,
        'valor': e['valor_total'] if e else base['valor_total'],
        'principal': (c or {}).get('principal') or (g or {}).get('principal'),
        'juros': (c or {}).get('juros') or (g or {}).get('juros') or ZERO,
        'multa': (c or {}).get('multa') or (g or {}).get('multa') or ZERO,
        'sentido': 'saida', 'descricao': descricao, 'chave': gr.get('chave') or '—',
        'documentos': [{'doc_id': x['doc_id'], 'doc_nome': x['doc_nome'], 'papel': x['tipo'],
                        'rotulo': x.get('rotulo'), 'ref': x['_ref']} for x in docs],
        'doc_ids': sorted({x['doc_id'] for x in docs}),
        '_guia': g, '_comprovante': c, '_extrato': e,
    }
    ids = p['doc_ids']
    if gr.get('ambiguo'):
        p['situacao'] = 'pendente'
        pend.append(_pend('P5', f'{descricao} ({brl(p["valor"])}): {len(gr["ambiguo"])} débitos do mesmo valor no extrato',
                          ids, pid))
    elif data is None:
        p['situacao'] = 'pendente'
        if c and c.get('agendamento'):
            pend.append(_pend('P3', f'{descricao}: comprovante de agendamento; só vale com o débito no extrato', ids, pid))
        elif c:
            conta = f' da conta {c["conta"]}' if c.get('conta') else ''
            pend.append(_pend('P3', f'{descricao}: o comprovante não traz a data do pagamento e não veio a guia '
                                    f'com o vencimento. Envie a guia ou o extrato{conta}.', ids, pid))
        else:
            pend.append(_pend('P2', f'{descricao} ({brl(p["valor"])}): sem débito no extrato (ainda não pago, '
                                    'ou pago por outra conta)', ids, pid))
    elif fonte == 'vencimento':
        pend.append(_pend('DV', f'{descricao}: o comprovante não traz a data do pagamento; lançado com o vencimento '
                                f'da guia ({data:%d/%m/%Y}). Se o extrato chegar, vale a data dele.', ids, pid))
    elif not e:
        pend.append(_pend('P4', f'{descricao}: lançado pela data do comprovante; falta o extrato da conta', ids, pid))
    if c and g and c.get('valor_total') is not None and g.get('valor_total') is not None:
        explicado = g['valor_total'] + (c.get('juros') or ZERO) + (c.get('multa') or ZERO) - (c.get('desconto') or ZERO)
        if c['valor_total'] != g['valor_total'] and c['valor_total'] != explicado:
            pend.append(_pend('P9', f'{descricao}: comprovante {brl(c["valor_total"])} × guia {brl(g["valor_total"])}', ids, pid))
    if p['situacao'] == 'ok' and (p['juros'] > ZERO or p['multa'] > ZERO):
        pend.append(_pend('JM', f'{descricao}: juros {brl(p["juros"])} e multa {brl(p["multa"])} vão no valor total; '
                                'separar em partidas depende da regra dela (MAPEAMENTO §12.4)', ids, pid))
    return p


def _pagamento_de_extrato(e):
    return {
        'id': 'F:' + (e.get('fitid') or e['_ref']), 'origem': 'extrato', 'situacao': 'ok',
        'data': e['data_efetiva'], 'fonte_data': 'extrato', 'valor': e['valor_total'], 'principal': e['valor_total'],
        'juros': ZERO, 'multa': ZERO, 'sentido': e['sentido'],
        'descricao': e.get('historico') or 'Linha do extrato', 'chave': 'Só extrato',
        'documentos': [{'doc_id': e['doc_id'], 'doc_nome': e['doc_nome'], 'papel': 'extrato_linha',
                        'rotulo': 'Linha do extrato', 'ref': e['_ref']}],
        'doc_ids': [e['doc_id']], '_guia': None, '_comprovante': None, '_extrato': e,
    }
