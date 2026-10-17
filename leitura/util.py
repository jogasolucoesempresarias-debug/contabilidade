"""Conversões comuns: dinheiro, data, CNPJ, competência e o formato serializável do fato."""
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

MESES = {'janeiro': 1, 'fevereiro': 2, 'março': 3, 'marco': 3, 'abril': 4, 'maio': 5, 'junho': 6,
         'julho': 7, 'agosto': 8, 'setembro': 9, 'outubro': 10, 'novembro': 11, 'dezembro': 12}

RE_DINHEIRO = re.compile(r'\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2}')
RE_DATA = re.compile(r'(?<!\d)(\d{2})/(\d{2})/(\d{4})(?!\d)')
RE_CNPJ = re.compile(r'(?<!\d)\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}(?!\d)')


def dinheiro(s):
    """'1.234,56' → Decimal('1234.56'). None se não houver valor."""
    if s is None:
        return None
    m = RE_DINHEIRO.search(str(s))
    if not m:
        return None
    try:
        return Decimal(m.group().replace('.', '').replace(',', '.')).quantize(Decimal('0.01'))
    except InvalidOperation:
        return None


def data_br(s):
    m = RE_DATA.search(s or '')
    if not m:
        return None
    d, mth, a = (int(x) for x in m.groups())
    try:
        return date(a, mth, d)
    except ValueError:
        return None


def so_digitos(s):
    return re.sub(r'\D', '', s or '')


def cnpj_valido(cnpj):
    d = so_digitos(cnpj)
    if len(d) != 14 or d == d[0] * 14:
        return False

    def dv(base):
        pesos = list(range(len(base) - 7, 1, -1)) + list(range(9, 1, -1))
        pesos = pesos[-len(base):]
        r = sum(int(n) * p for n, p in zip(base, pesos)) % 11
        return '0' if r < 2 else str(11 - r)

    return d[12] == dv(d[:12]) and d[13] == dv(d[:13])


def formatar_cnpj(cnpj):
    d = so_digitos(cnpj)
    if len(d) != 14:
        return cnpj
    return f'{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}'


def competencia_por_extenso(s):
    """'setembro/2026' → '09/2026'."""
    m = re.search(r'([a-zçA-ZÇ]+)\s*/\s*(\d{4})', s or '')
    if not m:
        return None
    mes = MESES.get(m.group(1).lower())
    return f'{mes:02d}/{m.group(2)}' if mes else None


def brl(v):
    """Decimal → '1.234,56' (para textos e telas)."""
    if v is None:
        return ''
    s = f'{v:,.2f}'
    return s.replace(',', 'X').replace('.', ',').replace('X', '.')


def normalizar_nome(s):
    """Para comparar nomes: maiúsculas, sem acento, sem sufixo societário."""
    import unicodedata
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode().upper()
    s = re.sub(r'[^A-Z0-9 ]', ' ', s)
    palavras = [p for p in s.split() if p not in {'LTDA', 'ME', 'EPP', 'EIRELI', 'SA', 'S', 'A', 'DE', 'DA', 'DO', 'DOS', 'DAS', 'E'}]
    return palavras


# ── Fato ⇄ JSON ──────────────────────────────────────────────────────
CAMPOS_DATA = {'data_efetiva', 'data_vencimento', 'data_emissao', 'data_geracao', 'pagar_ate'}
CAMPOS_VALOR = {'valor_total', 'principal', 'juros', 'multa', 'desconto', 'saldo'}


def fato_para_json(f):
    saida = {}
    for k, v in f.items():
        if isinstance(v, Decimal):
            saida[k] = str(v)
        elif isinstance(v, (date, datetime)):
            saida[k] = v.isoformat()
        elif k == 'composicao' and v:
            saida[k] = [{**c, **{x: str(c[x]) for x in ('principal', 'multa', 'juros', 'total') if c.get(x) is not None}} for c in v]
        else:
            saida[k] = v
    return saida


def fato_de_json(j):
    f = dict(j)
    for k in CAMPOS_DATA:
        if f.get(k):
            f[k] = date.fromisoformat(f[k][:10])
    for k in CAMPOS_VALOR:
        if f.get(k) is not None:
            f[k] = Decimal(f[k])
    if f.get('composicao'):
        f['composicao'] = [{**c, **{x: Decimal(c[x]) for x in ('principal', 'multa', 'juros', 'total') if c.get(x) is not None}} for c in f['composicao']]
    return f
