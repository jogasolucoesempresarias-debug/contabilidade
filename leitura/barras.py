"""Código de barras de boleto e de guia de arrecadação (padrão FEBRABAN).

Três formas do mesmo código aparecem nos documentos:
  - código de barras: 44 dígitos (o que o comprovante do Sicoob imprime);
  - linha digitável de arrecadação (guias, contas de consumo): 48 dígitos, 4 blocos de 11 + DV;
  - linha digitável de boleto bancário: 47 dígitos.

Tudo é normalizado para os 44 dígitos, que é a chave K1 do casamento (MAPEAMENTO §5).
O dígito verificador também confere o OCR: se o OCR trocar um dígito, o DV não fecha.
"""
import re
from datetime import date, timedelta
from decimal import Decimal
from itertools import product

# Trocas comuns do OCR em campo numérico. A fonte do comprovante Sicoob faz o 7 virar "/".
CONFUSAO_OCR = {'/': '7', 'O': '0', 'o': '0', 'D': '0', 'Q': '0', 'I': '1', 'l': '1', '|': '1',
                'i': '1', 'S': '5', 's': '5', 'B': '8', 'Z': '2', 'z': '2', 'G': '6', 'g': '9', 'q': '9'}


def so_digitos(s):
    return re.sub(r'\D', '', s or '')


# ── Dígitos verificadores ────────────────────────────────────────────
def mod10(s):
    tot, peso = 0, 2
    for ch in reversed(s):
        n = int(ch) * peso
        tot += n // 10 + n % 10
        peso = 1 if peso == 2 else 2
    r = tot % 10
    return 0 if r == 0 else 10 - r


def mod11_arrecadacao(s):
    tot, peso = 0, 2
    for ch in reversed(s):
        tot += int(ch) * peso
        peso = 2 if peso == 9 else peso + 1
    r = tot % 11
    if r in (0, 1):
        return 0
    return 1 if r == 10 else 11 - r


def mod11_boleto(s):
    """DV geral do boleto bancário: resto 0, 1 ou 10 vira 1."""
    tot, peso = 0, 2
    for ch in reversed(s):
        tot += int(ch) * peso
        peso = 2 if peso == 9 else peso + 1
    dv = 11 - tot % 11
    return 1 if dv in (0, 10, 11) else dv


def eh_arrecadacao(b44):
    return b44[:1] == '8'


def _dv_arrecadacao(b44):
    """Arrecadação: o 3º dígito diz o módulo (6/7 = mod10, 8/9 = mod11)."""
    return mod11_arrecadacao if b44[2] in '89' else mod10


def barras_valido(b44):
    if not (isinstance(b44, str) and len(b44) == 44 and b44.isdigit()):
        return False
    if eh_arrecadacao(b44):
        if b44[2] not in '6789':
            return False
        return int(b44[3]) == _dv_arrecadacao(b44)(b44[:3] + b44[4:])
    return int(b44[4]) == mod11_boleto(b44[:4] + b44[5:])


# ── Linha digitável ⇄ código de barras ───────────────────────────────
def linha_arrecadacao_para_barras(d48):
    blocos = [d48[i:i + 12] for i in range(0, 48, 12)]
    return ''.join(b[:11] for b in blocos)


def linha_arrecadacao_valida(d48):
    if len(d48) != 48 or d48[0] != '8' or d48[2] not in '6789':
        return False
    f = mod11_arrecadacao if d48[2] in '89' else mod10
    return all(int(b[11]) == f(b[:11]) for b in (d48[i:i + 12] for i in range(0, 48, 12)))


def linha_boleto_para_barras(d47):
    c1, c2, c3, dv, c5 = d47[0:10], d47[10:21], d47[21:32], d47[32], d47[33:47]
    campo_livre = c1[4:9] + c2[:10] + c3[:10]
    return c1[:3] + c1[3] + dv + c5 + campo_livre


def linha_boleto_valida(d47):
    if len(d47) != 47:
        return False
    campos = ((d47[0:9], d47[9]), (d47[10:20], d47[20]), (d47[21:31], d47[31]))
    return all(int(dv) == mod10(c) for c, dv in campos)


def normalizar(texto):
    """Qualquer forma (44, 47 ou 48 dígitos, com ou sem espaço) → 44 dígitos válidos, ou None."""
    d = so_digitos(texto)
    if len(d) == 44:
        b = d
    elif len(d) == 48 and linha_arrecadacao_valida(d):
        b = linha_arrecadacao_para_barras(d)
    elif len(d) == 47 and linha_boleto_valida(d):
        b = linha_boleto_para_barras(d)
    else:
        return None
    return b if barras_valido(b) else None


def linha_digitavel(b44):
    """44 dígitos → linha digitável formatada (para exibir e para o complemento)."""
    if eh_arrecadacao(b44):
        f = _dv_arrecadacao(b44)
        blocos = [b44[i:i + 11] for i in range(0, 44, 11)]
        return ' '.join(f'{b}-{f(b)}' for b in blocos)
    c1 = b44[0:4] + b44[19:24]
    c2 = b44[24:34]
    c3 = b44[34:44]
    return (f'{c1[:5]}.{c1[5:]}{mod10(c1)} {c2[:5]}.{c2[5:]}{mod10(c2)} '
            f'{c3[:5]}.{c3[5:]}{mod10(c3)} {b44[4]} {b44[5:19]}')


# ── O que o código carrega ───────────────────────────────────────────
def valor(b44):
    """Valor em reais embutido no código, ou None (arrecadação com 'valor de referência')."""
    if eh_arrecadacao(b44):
        if b44[2] not in '68':
            return None
        return (Decimal(int(b44[4:15])) / 100).quantize(Decimal('0.01'))
    v = int(b44[9:19])
    return (Decimal(v) / 100).quantize(Decimal('0.01')) if v else None


def vencimento_boleto(b44, referencia=None):
    """Fator de vencimento do boleto. O contador reiniciou em 22/02/2025 (fator 1000)."""
    if eh_arrecadacao(b44):
        return None
    fator = int(b44[5:9])
    if fator == 0:
        return None
    referencia = referencia or date.today()
    candidatos = [date(1997, 10, 7) + timedelta(days=fator),
                  date(2025, 2, 22) + timedelta(days=fator - 1000)]
    return min(candidatos, key=lambda d: abs((d - referencia).days))


def descrever(b44):
    if eh_arrecadacao(b44):
        return {'tipo': 'arrecadacao', 'segmento': b44[1], 'orgao': b44[15:19],
                'valor': valor(b44), 'campo_livre': b44[19:]}
    return {'tipo': 'boleto', 'banco': b44[:3], 'valor': valor(b44),
            'vencimento': vencimento_boleto(b44), 'campo_livre': b44[19:]}


# ── Encontrar códigos num texto ──────────────────────────────────────
_RE_ARREC = re.compile(r'(8\d{10})\s*-?\s*(\d)\s+(\d{11})\s*-?\s*(\d)\s+(\d{11})\s*-?\s*(\d)\s+(\d{11})\s*-?\s*(\d)')
_RE_BOLETO = re.compile(r'(\d{5})\.?(\d{5})\s+(\d{5})\.?(\d{6})\s+(\d{5})\.?(\d{6})\s+(\d)\s+(\d{14})')
_RE_44 = re.compile(r'(?<!\d)\d{44}(?!\d)')


def encontrar_codigos(texto):
    """Todos os códigos válidos no texto, sem repetição, na ordem em que aparecem."""
    achados = []
    for m in _RE_ARREC.finditer(texto):
        b = normalizar(''.join(m.groups()))
        if b:
            achados.append((m.start(), b))
    for m in _RE_BOLETO.finditer(texto):
        b = normalizar(''.join(m.groups()))
        if b:
            achados.append((m.start(), b))
    for m in _RE_44.finditer(texto):
        if barras_valido(m.group()):
            achados.append((m.start(), m.group()))
    vistos, saida = set(), []
    for _, b in sorted(achados):
        if b not in vistos:
            vistos.add(b)
            saida.append(b)
    return saida


# ── Conserto do OCR pelo dígito verificador ──────────────────────────
def consertar_ocr(texto, max_suspeitos=2):
    """Texto do OCR com caracteres trocados → código de 44 dígitos válido, ou None.

    Primeiro tenta a troca conhecida da tabela de confusão; se ela fechar o DV, vale. Senão,
    testa os 10 dígitos em cada posição suspeita e só aceita se exatamente UMA combinação fechar
    o DV (ambiguidade devolve None: melhor pendência do que código chutado).
    """
    s = re.sub(r'\s', '', texto or '')
    if not s:
        return None
    if s.isdigit():
        return normalizar(s)
    suspeitos = [i for i, c in enumerate(s) if not c.isdigit()]
    if len(suspeitos) > max_suspeitos:
        return None
    pela_tabela = ''.join(CONFUSAO_OCR.get(c, c) for c in s)
    if pela_tabela.isdigit():
        b = normalizar(pela_tabela)
        if b:
            return b
    validos = set()
    for combo in product('0123456789', repeat=len(suspeitos)):
        t = list(s)
        for i, d in zip(suspeitos, combo):
            t[i] = d
        b = normalizar(''.join(t))
        if b:
            validos.add(b)
    return validos.pop() if len(validos) == 1 else None


def digitos_ocr(texto):
    """Campo numérico SEM dígito verificador (nº de agendamento): aplica a tabela de confusão
    só com dígito dos DOIS lados. Assim "1234/567" vira "12347567", mas o separador de
    "12345/EMPRESA" continua barra."""
    s = texto or ''
    saida = []
    for i, c in enumerate(s):
        if c in CONFUSAO_OCR and 0 < i < len(s) - 1 and s[i - 1].isdigit() and s[i + 1].isdigit():
            saida.append(CONFUSAO_OCR[c])
        else:
            saida.append(c)
    return ''.join(saida)
