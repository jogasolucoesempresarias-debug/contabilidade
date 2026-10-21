"""Documentos reais de cliente NUNCA entram no repositório (que é público).

Os testes com amostras reais leem a pasta AMOSTRAS_DIR (do .env local), que traz os arquivos e
um `esperado.json` com os valores conferidos à mão. Sem essa pasta, esses testes são pulados e só
rodam os testes com dados inventados.
"""
import json
import os
import shutil
from datetime import date
from decimal import Decimal

import pytest
from dotenv import load_dotenv

load_dotenv()
_raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_dir = os.getenv('AMOSTRAS_DIR')
AMOSTRAS = os.path.normpath(os.path.join(_raiz, _dir)) if _dir else None
_esperado_arq = os.path.join(AMOSTRAS, 'esperado.json') if AMOSTRAS else None
ESPERADO = json.load(open(_esperado_arq, encoding='utf-8')) if _esperado_arq and os.path.exists(_esperado_arq) else None


def amostra(chave):
    if not ESPERADO:
        return None
    nome = ESPERADO[chave]['arquivo'] if isinstance(ESPERADO[chave], dict) else ESPERADO[chave]
    caminho = os.path.join(AMOSTRAS, nome)
    return caminho if os.path.exists(caminho) else None


def tem_tesseract():
    return bool(shutil.which('tesseract') or os.path.exists(r'C:\Program Files\Tesseract-OCR\tesseract.exe'))


precisa_amostras = pytest.mark.skipif(not amostra('das'), reason='amostras reais ausentes (AMOSTRAS_DIR)')
precisa_ocr = pytest.mark.skipif(not (amostra('das') and amostra('comprovante') and tem_tesseract()),
                                 reason='amostras reais ou Tesseract ausentes')


def ofx_teste(linhas, banco='756', agencia='0001', conta='99999'):
    """OFX SINTÉTICO, só para teste. linhas: [(fitid, date, Decimal com sinal, memo)]."""
    trn = ''.join(f'<STMTTRN><TRNTYPE>{"DEBIT" if v < 0 else "CREDIT"}<DTPOSTED>{d:%Y%m%d}120000[-3:BRT]'
                  f'<TRNAMT>{v}<FITID>{f}<MEMO>{m}</STMTTRN>\n' for f, d, v, m in linhas)
    return (f'OFXHEADER:100\nDATA:OFXSGML\nVERSION:102\nENCODING:USASCII\nCHARSET:1252\n\n'
            f'<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><CURDEF>BRL\n'
            f'<BANKACCTFROM><BANKID>{banco}<BRANCHID>{agencia}<ACCTID>{conta}</BANKACCTFROM>\n'
            f'<BANKTRANLIST><DTSTART>20260101<DTEND>20261231\n{trn}</BANKTRANLIST>'
            f'<LEDGERBAL><BALAMT>10000.00<DTASOF>20261231</LEDGERBAL>\n'
            f'</STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>\n').encode()


@pytest.fixture(scope='session')
def leitura_das():
    from leitura import ler_arquivo
    return ler_arquivo(open(amostra('das'), 'rb').read())


@pytest.fixture(scope='session')
def leitura_comprovante():
    from leitura import ler_arquivo
    return ler_arquivo(open(amostra('comprovante'), 'rb').read())


def data_debito():
    """Dia do débito no extrato sintético = dia do pagamento do comprovante real."""
    return date.fromisoformat(ESPERADO['comprovante']['data_pagamento'])


@pytest.fixture(scope='session')
def leitura_ofx_do_das(leitura_das):
    """Extrato sintético com o débito do DAS real no dia do pagamento + uma tarifa + um PIX
    recebido. Os valores vêm dos documentos lidos (nada de dado real escrito no código)."""
    from leitura import ler_arquivo
    das = leitura_das['fatos'][0]
    dia = data_debito()
    return ler_arquivo(ofx_teste([
        ('T001', dia.replace(day=5), Decimal('-49.90'), 'TARIFA PACOTE SERVICOS'),
        ('T002', dia, -das['valor_total'], 'DEB.CONV.SIMPLES NACIONAL'),
        ('T003', dia.replace(day=21), Decimal('1500.00'), 'PIX RECEBIDO CLIENTE X'),
    ], conta=ESPERADO['comprovante']['conta']))


def d(iso):
    return date.fromisoformat(iso)
