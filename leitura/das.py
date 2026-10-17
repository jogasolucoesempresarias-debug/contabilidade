"""DAS — Documento de Arrecadação do Simples Nacional (PDF com texto, gerado pelo PGDAS-D).

Validado com um DAS real da primeira cliente. Campos: CNPJ, razão social, período de apuração,
vencimento, número do documento, composição por tributo (principal/multa/juros/total), total e
código de barras.
"""
import re
from decimal import Decimal

from . import barras
from .util import (RE_CNPJ, RE_DINHEIRO, cnpj_valido, competencia_por_extenso, data_br,
                   dinheiro, formatar_cnpj)

RE_NUMERO = re.compile(r'\d{2}\.\d{2}\.\d{5}\.\d{7}-\d')
COLUNAS = ('Principal', 'Multa', 'Juros', 'Total')


def reconhece(texto):
    t = texto.lower()
    return 'documento de arrecadação' in t and 'simples nacional' in t


def _composicao(palavras):
    """Linhas da composição, cada número na coluna cujo cabeçalho está mais perto (pela borda
    direita, porque os valores são alinhados à direita)."""
    cab = next((w for w in palavras if w['text'] == 'Principal'), None)
    if not cab:
        return []
    cabecalho = {w['text']: w['x1'] for w in palavras
                 if w['text'] in COLUNAS and abs(w['top'] - cab['top']) < 3}
    if len(cabecalho) < 2:
        return []
    fim = next((w['top'] for w in palavras if w['text'] == 'Totais' and w['top'] > cab['top']), 10 ** 6)
    # Agrupa por linha com tolerância: no DAS o código do tributo fica ~2 pt acima dos valores.
    corpo = sorted((w for w in palavras if cab['top'] + 3 < w['top'] < fim - 1), key=lambda w: w['top'])
    linhas, atual = [], []
    for w in corpo:
        if atual and w['top'] - atual[0]['top'] > 4:
            linhas.append(atual)
            atual = []
        atual.append(w)
    if atual:
        linhas.append(atual)
    saida = []
    for ws in linhas:
        ws.sort(key=lambda w: w['x0'])
        if not re.fullmatch(r'\d{4}', ws[0]['text']):
            continue                      # linha da competência ("09/2026") embaixo de cada tributo
        nums = [w for w in ws[1:] if RE_DINHEIRO.fullmatch(w['text'])]
        desc = ' '.join(w['text'] for w in ws[1:] if w not in nums)
        item = {'codigo': ws[0]['text'], 'descricao': desc}
        for n in nums:
            coluna = min(cabecalho, key=lambda c: abs(cabecalho[c] - n['x1']))
            item[coluna.lower()] = dinheiro(n['text'])
        saida.append(item)
    return saida


def ler(texto, palavras_pagina1):
    if not reconhece(texto):
        return None
    avisos = []
    m_cnpj = RE_CNPJ.search(texto)
    cnpj = formatar_cnpj(m_cnpj.group()) if m_cnpj else None
    razao = None
    if m_cnpj:
        linha = texto[m_cnpj.end():].split('\n', 1)[0].strip()
        razao = linha or None
    if cnpj and not cnpj_valido(cnpj):
        avisos.append('CNPJ da guia com dígito verificador inválido')

    competencia = competencia_por_extenso(texto)
    if not competencia:
        m = re.search(r'Per[ií]odo de Apura[çc][ãa]o\s*:?\s*(\d{2}/\d{4})', texto)
        competencia = m.group(1) if m else None

    vencimento = None
    for linha in texto.split('\n'):
        if competencia_por_extenso(linha) or (competencia and competencia in linha):
            vencimento = data_br(linha.split(competencia)[-1] if competencia in linha else linha)
            if vencimento:
                break
    m_pagar = re.search(r'Pagar at[ée]:?\s*(\d{2}/\d{2}/\d{4})', texto)
    pagar_ate = data_br(m_pagar.group(1)) if m_pagar else None

    m_num = RE_NUMERO.search(texto)
    m_total = re.search(r'Valor Total do Documento\s*\n?\s*(' + RE_DINHEIRO.pattern + ')', texto)
    total = dinheiro(m_total.group(1)) if m_total else None

    composicao = _composicao(palavras_pagina1 or [])
    soma = lambda campo: sum((c.get(campo) or Decimal('0')) for c in composicao).quantize(Decimal('0.01'))
    if composicao:
        if total is not None and soma('total') != total:
            avisos.append(f'Soma da composição ({soma("total")}) diferente do total ({total})')
    else:
        avisos.append('Composição por tributo não lida')

    codigos = barras.encontrar_codigos(texto)
    b44 = codigos[0] if codigos else None
    if not b44:
        avisos.append('Código de barras não encontrado')
    elif total is not None and barras.valor(b44) != total:
        avisos.append('Valor do código de barras diferente do total da guia')

    return {
        'tipo': 'guia', 'subtipo': 'DAS', 'rotulo': 'DAS',
        'cnpj_documento': cnpj, 'razao_social': razao,
        'contraparte_nome': 'Receita Federal — Simples Nacional',
        'competencia': competencia, 'data_vencimento': vencimento, 'pagar_ate': pagar_ate,
        'numero_documento': m_num.group() if m_num else None,
        'valor_total': total,
        'principal': soma('principal') if composicao else total,
        'multa': soma('multa') if composicao else Decimal('0.00'),
        'juros': soma('juros') if composicao else Decimal('0.00'),
        'composicao': composicao,
        'barras44': b44, 'linha_digitavel': barras.linha_digitavel(b44) if b44 else None,
        'sentido': 'saida', 'avisos': avisos,
    }
