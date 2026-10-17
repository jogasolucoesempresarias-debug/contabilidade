"""Comprovante de pagamento do Sicoob (convênio/boleto), lido por OCR.

Validado com um comprovante real da primeira cliente: PDF gerado pelo iPhone, uma imagem só.
A segunda via sai "Pagamento realizado com sucesso", mas com a data em branco ("Pagamento
efetuado null") e com "Número do agendamento". Conta como pago (decisão de 17/10); sem data,
vale o extrato ou o vencimento da guia.
"""
import re

from . import barras
from .util import data_br, dinheiro

ROTULOS = ('Convênio', 'Cód. de barras', 'Número do agendamento', 'Valor do documento',
           'Valor dos juros', 'Valor da multa', 'Valor do desconto', 'Valor total', 'Pagador',
           'Nome/Razão social', 'Cooperativa', 'Conta debitada', 'Autenticação', 'Beneficiário',
           'Data do pagamento', 'Data de pagamento')


def reconhece(texto):
    t = texto.upper()
    return 'SICOOB' in t and 'COMPROVANTE' in t


def _sem_acento(s):
    import unicodedata
    return unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()


def _eh_rotulo(linha):
    l = _sem_acento(linha).strip()
    return any(l.startswith(_sem_acento(r).lower()) for r in ROTULOS)


def _apos(linhas, rotulo, juntar_ate_proximo=False):
    """Valor que vem depois do rótulo: no resto da mesma linha ou na(s) linha(s) seguinte(s)."""
    alvo = _sem_acento(rotulo)
    for i, linha in enumerate(linhas):
        if _sem_acento(linha).strip().startswith(alvo):
            resto = linha.strip()[len(rotulo):].strip(' :')
            if resto and not juntar_ate_proximo:
                return resto
            partes = [resto] if resto else []
            for prox in linhas[i + 1:]:
                if not prox.strip():
                    continue
                if _eh_rotulo(prox):
                    break
                partes.append(prox.strip())
                if not juntar_ate_proximo:
                    break
            return ' '.join(partes) or None
    return None


def ler(texto):
    if not reconhece(texto):
        return None
    linhas = [l for l in texto.split('\n')]
    avisos = []

    texto_barras = _apos(linhas, 'Cód. de barras', juntar_ate_proximo=True)
    b44 = barras.consertar_ocr(texto_barras) if texto_barras else None
    if texto_barras and not b44:
        avisos.append('Código de barras ilegível (o dígito verificador não fecha)')

    total = dinheiro(_apos(linhas, 'Valor total'))
    principal = dinheiro(_apos(linhas, 'Valor do documento'))
    juros = dinheiro(_apos(linhas, 'Valor dos juros'))
    multa = dinheiro(_apos(linhas, 'Valor da multa'))
    desconto = dinheiro(_apos(linhas, 'Valor do desconto'))
    if b44 and total is not None and barras.valor(b44) not in (None, total, principal):
        avisos.append('Valor do código de barras não bate com o comprovante')

    agendamento_txt = _apos(linhas, 'Número do agendamento')
    numero_agendamento = barras.so_digitos(barras.digitos_ocr(agendamento_txt)) if agendamento_txt else None
    # "Número do agendamento" aparece também em pagamento feito na hora; o que diz se foi só
    # agendado é o título ("Pagamento agendado", "Agendamento realizado").
    so_agendado = bool(re.search(r'pagamento agendado|agendamento (realizado|efetuado|confirmado)', texto, re.I))

    data_achada = None
    m = re.search(r'Pagamento efetuado\s+(?:em\s+)?(\d{2}/\d{2}/\d{4})', texto, re.I)
    if m:
        data_achada = data_br(m.group(1))
    else:
        data_achada = data_br(_apos(linhas, 'Data do pagamento') or _apos(linhas, 'Data de pagamento') or '')
    if so_agendado:
        avisos.append('Comprovante de agendamento: só vale com o débito no extrato')
    elif not data_achada:
        avisos.append('O comprovante não informa a data do pagamento: vale o extrato ou, sem ele, o vencimento da guia')
    m_ger = re.search(r'gerado em\s+(\d{2}/\d{2}/\d{4})', texto, re.I)

    conta_txt = _apos(linhas, 'Conta debitada') or ''
    m_conta = re.match(r'\s*([\dOIl|/]+?)\s*/\s*(.+)$', conta_txt)
    conta = barras.so_digitos(barras.digitos_ocr(m_conta.group(1))) if m_conta else None
    titular = m_conta.group(2).strip() if m_conta else None

    aut = re.search(r'([0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12})', texto)
    convenio = _apos(linhas, 'Convênio')

    descricao = None
    for i, l in enumerate(linhas[:8]):
        if re.search(r'Pagamento efetuado', l, re.I):
            prox = next((x.strip() for x in linhas[i + 1:i + 3] if x.strip()), None)
            descricao = prox
            break

    if not (b44 and total is not None):
        avisos.append('Campos principais não lidos com segurança')

    return {
        'tipo': 'comprovante', 'subtipo': 'Sicoob', 'rotulo': 'Comprovante Sicoob',
        'forma': 'convenio' if convenio else ('boleto' if b44 else 'desconhecida'),
        'convenio': convenio, 'descricao': descricao,
        'barras44': b44, 'valor_total': total, 'principal': principal, 'juros': juros,
        'multa': multa, 'desconto': desconto,
        'data_efetiva': None if so_agendado else data_achada,
        'data_agendada': data_achada if so_agendado else None,
        'data_geracao': data_br(m_ger.group(1)) if m_ger else None,
        'agendamento': so_agendado, 'numero_agendamento': numero_agendamento,
        'pagador_nome': _apos(linhas, 'Nome/Razão social'),
        'banco': '756', 'banco_nome': _apos(linhas, 'Cooperativa'),
        'conta': conta, 'titular_conta': titular,
        'autenticacao': aut.group(1) if aut else None,
        'sentido': 'saida', 'avisos': avisos,
    }
