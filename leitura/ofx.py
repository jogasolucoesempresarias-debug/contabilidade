"""Extrato em OFX. Banco brasileiro costuma mandar OFX 1.x (SGML, sem fechar as tags, em
latin-1/cp1252). O leitor aceita SGML e XML sem depender de biblioteca.
"""
import re
from datetime import date
from decimal import Decimal, InvalidOperation


def _decodificar(conteudo):
    cab = conteudo[:600].upper()
    if b'ENCODING="UTF-8"' in cab or b'CHARSET:UTF-8' in cab:
        try:
            return conteudo.decode('utf-8')
        except UnicodeDecodeError:
            pass
    try:
        return conteudo.decode('utf-8')
    except UnicodeDecodeError:
        return conteudo.decode('cp1252', errors='replace')


def _tag(bloco, nome):
    m = re.search(r'<' + nome + r'>\s*([^<\r\n]*)', bloco, re.I)
    return m.group(1).strip() if m else None


def _data(s):
    if not s or len(s) < 8 or not s[:8].isdigit():
        return None
    try:
        return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    except ValueError:
        return None


def _valor(s):
    try:
        return Decimal((s or '').replace(',', '.')).quantize(Decimal('0.01'))
    except InvalidOperation:
        return None


def ler(conteudo):
    """Uma linha de extrato (fato 'extrato_linha') por transação + resumo da conta."""
    txt = _decodificar(conteudo)
    banco = _tag(txt, 'BANKID')
    agencia = _tag(txt, 'BRANCHID')
    conta = _tag(txt, 'ACCTID')
    saldo_final = _valor(_tag(txt, 'BALAMT'))
    linhas, avisos = [], []
    for bloco in re.findall(r'<STMTTRN>(.*?)(?=</STMTTRN>|<STMTTRN>|</BANKTRANLIST>)', txt, re.S | re.I):
        valor = _valor(_tag(bloco, 'TRNAMT'))
        data = _data(_tag(bloco, 'DTPOSTED'))
        if valor is None or data is None:
            avisos.append('Transação sem data ou valor ignorada')
            continue
        memo = _tag(bloco, 'MEMO') or ''
        nome = _tag(bloco, 'NAME') or ''
        historico = ' '.join(x for x in (nome, memo) if x and x not in ('-',)) or (_tag(bloco, 'TRNTYPE') or '')
        linhas.append({
            'tipo': 'extrato_linha', 'subtipo': 'ofx', 'rotulo': 'Linha do extrato',
            'data_efetiva': data, 'valor_total': abs(valor),
            'sentido': 'saida' if valor < 0 else 'entrada',
            'historico': historico.strip(), 'fitid': _tag(bloco, 'FITID'),
            'numero_documento': _tag(bloco, 'CHECKNUM') or _tag(bloco, 'REFNUM'),
            'banco': banco, 'agencia': agencia, 'conta': conta,
        })
    if not linhas:
        avisos.append('Nenhuma transação encontrada no OFX')
    resumo = {'banco': banco, 'agencia': agencia, 'conta': conta, 'saldo_final': saldo_final,
              'inicio': _data(_tag(txt, 'DTSTART')), 'fim': _data(_tag(txt, 'DTEND')),
              'transacoes': len(linhas)}
    return linhas, resumo, avisos
