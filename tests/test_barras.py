"""Código de barras com valores INVENTADOS (o repositório é público). O caso real da primeira
cliente é conferido em test_leitura.py, com os valores lidos de AMOSTRAS_DIR/esperado.json."""
import re
from datetime import date
from decimal import Decimal

from leitura import barras


def _arrecadacao(valor_centavos=123456, orgao='0328', campo_livre='7234567890123456789012345'):
    """Guia de órgão público (segmento 5, valor real, módulo 11), como um DAS."""
    sem_dv = '858' + f'{valor_centavos:011d}' + orgao + campo_livre
    return sem_dv[:3] + str(barras.mod11_arrecadacao(sem_dv)) + sem_dv[3:]


def _como_comprovante(b44):
    """O comprovante do Sicoob imprime os 44 dígitos em grupos de 11-1-11-1-11-1-8."""
    tam = [11, 1, 11, 1, 11, 1, 8]
    partes, i = [], 0
    for t in tam:
        partes.append(b44[i:i + t])
        i += t
    return ' '.join(partes)


BARRAS = _arrecadacao()
LINHA = barras.linha_digitavel(BARRAS)                    # forma impressa na guia (48 dígitos)
COMPROVANTE = _como_comprovante(BARRAS)


def test_linha_da_guia_e_codigo_do_comprovante_viram_o_mesmo_codigo():
    assert len(barras.so_digitos(LINHA)) == 48
    assert barras.normalizar(LINHA) == BARRAS
    assert barras.normalizar(COMPROVANTE) == BARRAS


def test_dvs_conferem_e_valor_embutido():
    assert barras.linha_arrecadacao_valida(barras.so_digitos(LINHA))
    assert barras.barras_valido(BARRAS)
    assert barras.valor(BARRAS) == Decimal('1234.56')
    d = barras.descrever(BARRAS)
    assert d['segmento'] == '5' and d['orgao'] == '0328'


def test_ocr_com_barra_no_lugar_do_7_e_consertado():
    i = BARRAS.index('7', 20)                              # um 7 no meio do código
    ocr = COMPROVANTE.replace(' ', '')
    ocr = ocr[:i] + '/' + ocr[i + 1:]
    assert not barras.barras_valido(ocr)
    assert barras.consertar_ocr(ocr[:30] + ' ' + ocr[30:] + '\n') == BARRAS


def test_um_digito_errado_nao_passa():
    errado = BARRAS[:20] + ('1' if BARRAS[20] != '1' else '2') + BARRAS[21:]
    assert not barras.barras_valido(errado)
    assert barras.normalizar(errado) is None


def test_conserto_ambiguo_devolve_none():
    # dois caracteres desconhecidos sem troca conhecida: várias combinações fecham o DV
    s = BARRAS[:10] + '?' + BARRAS[11:30] + '?' + BARRAS[31:]
    assert barras.consertar_ocr(s) is None


def test_encontrar_codigos_no_texto():
    texto = 'Documento de Arrecadação\nValor: 1.234,56\n' + re.sub(r'(-\d) ', r'\1\n', LINHA).replace('-', ' ') + '\nCNPJ'
    assert barras.encontrar_codigos(texto) == [BARRAS]


def test_digitos_ocr_so_troca_entre_digitos():
    assert barras.digitos_ocr('1234/567') == '12347567'
    assert barras.digitos_ocr('12345/EMPRESA') == '12345/EMPRESA'


def _boleto(banco='756', fator=2240, valor_centavos=123456, campo_livre='1' * 25):
    sem_dv = f'{banco}9' + f'{fator:04d}{valor_centavos:010d}' + campo_livre
    dv = barras.mod11_boleto(sem_dv)
    return sem_dv[:4] + str(dv) + sem_dv[4:]


def test_boleto_ida_e_volta_pela_linha_digitavel():
    b = _boleto()
    assert barras.barras_valido(b)
    linha = barras.linha_digitavel(b)
    assert len(barras.so_digitos(linha)) == 47
    assert barras.normalizar(linha) == b
    assert barras.valor(b) == Decimal('1234.56')


def test_vencimento_do_boleto_no_ciclo_novo():
    # fator 1000 = 22/02/2025 no ciclo que começou em 2025
    b = _boleto(fator=1000)
    assert barras.vencimento_boleto(b, referencia=date(2026, 10, 17)) == date(2025, 2, 22)
    fator = 1000 + (date(2026, 10, 20) - date(2025, 2, 22)).days
    b2 = _boleto(fator=fator)
    assert barras.vencimento_boleto(b2, referencia=date(2026, 10, 17)) == date(2026, 10, 20)
