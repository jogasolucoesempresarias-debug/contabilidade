"""Boleto ou guia que não tem leitor próprio: lido só pela linha digitável (vale para qualquer
banco). O código dá valor e, no boleto, vencimento. Beneficiário e o resto ficam para os
leitores da fase 3 — por isso o documento entra com aviso.
"""
import re

from . import barras
from .util import RE_CNPJ, formatar_cnpj


def ler(texto):
    codigos = barras.encontrar_codigos(texto)
    if not codigos:
        return None
    b44 = codigos[0]
    info = barras.descrever(b44)
    avisos = ['Lido só pelo código de barras: beneficiário e referência não identificados nesta versão']
    if len(codigos) > 1:
        avisos.append(f'{len(codigos)} códigos de barras no mesmo arquivo; usado o primeiro')
    beneficiario_cnpj = None
    m = re.search(r'Benefici[áa]rio[^\n]*\n?[^\n]*?(' + RE_CNPJ.pattern + ')', texto, re.I)
    if m:
        beneficiario_cnpj = formatar_cnpj(m.group(1))
    arrecadacao = info['tipo'] == 'arrecadacao'
    return {
        'tipo': 'guia' if arrecadacao else 'boleto',
        'subtipo': 'arrecadacao' if arrecadacao else 'boleto',
        'rotulo': 'Guia (código de barras)' if arrecadacao else 'Boleto',
        'barras44': b44, 'linha_digitavel': barras.linha_digitavel(b44),
        'valor_total': info['valor'], 'principal': info['valor'],
        'data_vencimento': info.get('vencimento'),
        'contraparte_cnpj': beneficiario_cnpj,
        'banco': info.get('banco'),
        'sentido': 'saida', 'avisos': avisos,
    }
