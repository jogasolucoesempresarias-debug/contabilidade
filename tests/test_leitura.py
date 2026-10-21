from decimal import Decimal

import pytest

from leitura import entrada, ler_arquivo
from tests.conftest import ESPERADO, d, ofx_teste, precisa_amostras, precisa_ocr


@precisa_amostras
def test_das_real(leitura_das):
    esp = ESPERADO['das']
    r = leitura_das
    assert r['tipo'] == 'DAS' and r['origem'] == 'texto' and r['avisos'] == []
    f = r['fatos'][0]
    assert f['cnpj_documento'] == esp['cnpj']
    assert f['razao_social'] == esp['razao_social']
    assert f['competencia'] == esp['competencia']
    assert f['data_vencimento'] == d(esp['vencimento'])
    assert f['numero_documento'] == esp['numero']
    assert f['valor_total'] == Decimal(esp['total'])
    assert f['barras44'] == esp['barras44']
    assert {c['codigo']: c['total'] for c in f['composicao']} == {k: Decimal(v) for k, v in esp['composicao'].items()}


@precisa_ocr
def test_comprovante_sicoob_real_por_ocr(leitura_comprovante):
    esp = ESPERADO['comprovante']
    r = leitura_comprovante
    assert r['tipo'] == 'Comprovante Sicoob' and r['origem'] == 'ocr'
    assert r['confianca'] >= 0.80
    f = r['fatos'][0]
    assert f['barras44'] == esp['barras44']             # consertado pelo DV (o OCR troca 7 por "/")
    assert f['valor_total'] == Decimal(esp['total'])
    assert f['juros'] == Decimal(esp['juros']) and f['multa'] == Decimal(esp['multa'])
    assert f['conta'] == esp['conta']
    assert f['numero_agendamento'] == esp['agendamento']
    # "Pagamento efetuado null": a data do pagamento é o "gerado em" do quadro azul (21/10)
    assert f['data_efetiva'] == d(esp['data_pagamento']) and f['origem_data'] == 'gerado_em'
    assert f['hora_pagamento'] == esp['hora_pagamento']
    assert r['avisos'] == []


def test_ofx_sintetico():
    r = ler_arquivo(ofx_teste([('A1', d('2026-03-10'), Decimal('-250.00'), 'PAGAMENTO BOLETO'),
                               ('A2', d('2026-03-11'), Decimal('80.00'), 'PIX RECEBIDO')], conta='12345'))
    assert r['tipo'] == 'Extrato OFX' and len(r['fatos']) == 2
    pg = next(f for f in r['fatos'] if f['fitid'] == 'A1')
    assert pg['data_efetiva'] == d('2026-03-10') and pg['valor_total'] == Decimal('250.00')
    assert pg['sentido'] == 'saida' and pg['conta'] == '12345'
    assert next(f for f in r['fatos'] if f['fitid'] == 'A2')['sentido'] == 'entrada'


@pytest.mark.parametrize('cabeca', [
    b'\xff\xd8\xff\xe0' + b'\x00' * 20,                       # JPEG
    b'\x89PNG\r\n\x1a\n' + b'\x00' * 20,                      # PNG
    b'\x00\x00\x00\x18ftypheic' + b'\x00' * 20,               # HEIC do iPhone
])
def test_imagem_e_recusada(cabeca):
    with pytest.raises(entrada.ArquivoRecusado) as e:
        entrada.identificar(cabeca)
    assert 'PDF' in str(e.value)


def test_formatos_aceitos():
    assert entrada.identificar(b'%PDF-1.5\n...') == 'pdf'
    assert entrada.identificar(b'OFXHEADER:100\nDATA:OFXSGML') == 'ofx'
    assert entrada.identificar(b'<?xml version="1.0"?><nfeProc/>') == 'xml'
    with pytest.raises(entrada.ArquivoRecusado):
        entrada.identificar(b'PK\x03\x04 planilha zipada')
