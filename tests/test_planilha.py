from datetime import date
from decimal import Decimal

import pytest
import xlrd

import planilha
from tests.conftest import amostra

# Linha inventada (o repositório é público).
LINHA = {'lancto_auto': '00007', 'debito': None, 'credito': None, 'data': date(2026, 3, 20),
         'valor': Decimal('1234.56'), 'cod_historico': 31, 'complemento': 'DAS 02/2026 Nº 00.00.00000.0000000-0',
         'ccusto_d': None, 'ccusto_c': None, 'nr_documento': '00001'}


def _abrir(conteudo):
    b = xlrd.open_workbook(file_contents=conteudo, formatting_info=True)
    return b, b.sheet_by_index(0)


@pytest.mark.skipif(not amostra('modelo_xls'), reason='modelo do escritório ausente (AMOSTRAS_DIR)')
def test_cabecalho_igual_ao_modelo():
    _, modelo = _abrir(open(amostra('modelo_xls'), 'rb').read())
    _, gerado = _abrir(planilha.gerar_xls([LINHA]))
    assert gerado.name == modelo.name == 'Planilha1'
    assert [gerado.cell_value(0, c) for c in range(10)] == [modelo.cell_value(0, c) for c in range(10)]


def test_tipos_de_celula():
    b, sh = _abrir(planilha.gerar_xls([LINHA]))
    assert sh.cell(1, 0).ctype == xlrd.XL_CELL_TEXT and sh.cell_value(1, 0) == '00007'
    assert sh.cell(1, 9).ctype == xlrd.XL_CELL_TEXT and sh.cell_value(1, 9) == '00001'
    assert sh.cell(1, 3).ctype == xlrd.XL_CELL_DATE
    assert xlrd.xldate_as_datetime(sh.cell_value(1, 3), b.datemode).date() == date(2026, 3, 20)
    assert b.format_map[b.xf_list[sh.cell(1, 3).xf_index].format_key].format_str == 'dd/mm/yyyy'
    assert sh.cell_value(1, 4) == 1234.56
    assert sh.cell(1, 1).ctype == xlrd.XL_CELL_EMPTY and sh.cell(1, 2).ctype == xlrd.XL_CELL_EMPTY


def test_lancto_auto_em_branco_continua_texto():
    _, sh = _abrir(planilha.gerar_xls([{**LINHA, 'lancto_auto': ''}]))
    assert sh.cell_value(1, 0) == ''
