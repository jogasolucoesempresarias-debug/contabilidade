"""Casamento com os documentos reais (lidos de AMOSTRAS_DIR). As asserções são RELAÇÕES entre os
documentos (data = vencimento da guia, valor = total da guia…), sem dado real escrito aqui."""
from datetime import date
from decimal import Decimal

import casamento
import planilha
from tests.conftest import precisa_amostras, precisa_ocr

REGRA_DAS_SEM_CODIGO = {'id': 1, 'empresa_id': None, 'gatilho': 'tipo_doc', 'valor': 'DAS', 'lancto_auto': '',
                        'cod_historico': None, 'modelo_complemento': 'DAS {competencia} Nº {numero}',
                        'descricao': 'DAS (Simples Nacional)', 'ativa': True}
OUTRA_EMPRESA = {'id': 2, 'cnpj': '11.222.333/0001-81'}      # CNPJ inventado (DV válido)


def _empresa(leitura_das):
    return {'id': 1, 'cnpj': leitura_das['fatos'][0]['cnpj_documento']}


def _doc(i, nome, leitura):
    return {'id': i, 'nome': nome, 'reconhecido': leitura['reconhecido'], 'origem': leitura['origem'],
            'confianca': leitura['confianca'], 'fatos': leitura['fatos']}


def _codigos(res):
    return sorted(p['codigo'] for p in res['pendencias'])


def _complemento(das):
    return f'DAS {das["competencia"]} Nº {das["numero_documento"]}'


@precisa_ocr
def test_das_mais_comprovante_sem_data_usa_o_vencimento(leitura_das, leitura_comprovante):
    """Os dois documentos da cliente: segunda via de pagamento sem data → vencimento da guia
    (decisão de 17/10), com aviso informativo DV."""
    das = leitura_das['fatos'][0]
    docs = [_doc(1, 'das.pdf', leitura_das), _doc(2, 'comprovante.pdf', leitura_comprovante)]
    res = casamento.calcular(docs, _empresa(leitura_das), [REGRA_DAS_SEM_CODIGO])
    assert len(res['pagamentos']) == 1                  # dois documentos, UM pagamento
    p = res['pagamentos'][0]
    assert p['chave'] == 'Código de barras' and p['situacao'] == 'ok'
    assert p['data'] == das['data_vencimento'] and p['fonte_data'] == 'vencimento'
    assert _codigos(res) == ['CL', 'DV']                # falta o código; data pelo vencimento
    linhas = planilha.linhas(res['pagamentos'])
    assert len(linhas) == 1 and linhas[0]['data'] == das['data_vencimento']
    assert linhas[0]['complemento'] == _complemento(das)


@precisa_ocr
def test_agendamento_sem_extrato_continua_parado(leitura_das, leitura_comprovante):
    agendado = {**leitura_comprovante, 'fatos': [{**leitura_comprovante['fatos'][0], 'agendamento': True}]}
    res = casamento.calcular([_doc(1, 'das.pdf', leitura_das), _doc(2, 'agendamento.pdf', agendado)],
                             _empresa(leitura_das), [REGRA_DAS_SEM_CODIGO])
    assert _codigos(res) == ['P3'] and planilha.linhas(res['pagamentos']) == []


@precisa_ocr
def test_comprovante_sem_data_e_sem_guia_continua_parado(leitura_das, leitura_comprovante):
    res = casamento.calcular([_doc(2, 'comprovante.pdf', leitura_comprovante)], _empresa(leitura_das),
                             [REGRA_DAS_SEM_CODIGO])
    assert _codigos(res) == ['P3'] and planilha.linhas(res['pagamentos']) == []


@precisa_ocr
def test_com_extrato_vale_a_data_do_extrato(leitura_das, leitura_comprovante, leitura_ofx_do_das):
    das = leitura_das['fatos'][0]
    docs = [_doc(1, 'das.pdf', leitura_das), _doc(2, 'comprovante.pdf', leitura_comprovante),
            _doc(3, 'extrato.ofx', leitura_ofx_do_das)]
    res = casamento.calcular(docs, _empresa(leitura_das), [REGRA_DAS_SEM_CODIGO])
    pg = next(p for p in res['pagamentos'] if p['id'].startswith('B:'))
    assert pg['situacao'] == 'ok' and pg['data'] == das['data_vencimento'] and pg['fonte_data'] == 'extrato'
    assert pg['valor'] == das['valor_total']
    assert pg['chave'] == 'Código de barras + valor e data'
    assert len(pg['documentos']) == 3                   # extrato + comprovante + guia
    # tarifa e PIX recebido não têm regra; DAS ainda sem o código do lançamento automático
    assert _codigos(res) == ['CL', 'P1', 'P1']
    linhas = planilha.linhas(res['pagamentos'])
    assert len(linhas) == 1 and linhas[0]['complemento'] == _complemento(das)
    assert linhas[0]['lancto_auto'] == '' and linhas[0]['nr_documento'] == '00001'


@precisa_ocr
def test_com_codigo_na_regra_nao_ha_pendencia_do_das(leitura_das, leitura_comprovante, leitura_ofx_do_das):
    regra = {**REGRA_DAS_SEM_CODIGO, 'lancto_auto': '00007', 'cod_historico': 31}
    docs = [_doc(1, 'das.pdf', leitura_das), _doc(2, 'comprovante.pdf', leitura_comprovante),
            _doc(3, 'extrato.ofx', leitura_ofx_do_das)]
    res = casamento.calcular(docs, _empresa(leitura_das), [regra])
    assert 'CL' not in _codigos(res)
    assert planilha.linhas(res['pagamentos'])[0]['lancto_auto'] == '00007'


@precisa_amostras
def test_guia_sozinha_nao_vira_lancamento(leitura_das):
    res = casamento.calcular([_doc(1, 'das.pdf', leitura_das)], _empresa(leitura_das), [REGRA_DAS_SEM_CODIGO])
    assert _codigos(res) == ['P2'] and planilha.linhas(res['pagamentos']) == []


@precisa_amostras
def test_guia_mais_extrato_sem_comprovante(leitura_das, leitura_ofx_do_das):
    das = leitura_das['fatos'][0]
    res = casamento.calcular([_doc(1, 'das.pdf', leitura_das), _doc(3, 'extrato.ofx', leitura_ofx_do_das)],
                             _empresa(leitura_das), [REGRA_DAS_SEM_CODIGO])
    pg = next(p for p in res['pagamentos'] if p['id'].startswith('B:'))
    assert pg['data'] == das['data_vencimento'] and pg['chave'] == 'Valor e data'


@precisa_amostras
def test_guia_de_outra_empresa(leitura_das):
    res = casamento.calcular([_doc(1, 'das.pdf', leitura_das)], OUTRA_EMPRESA, [REGRA_DAS_SEM_CODIGO])
    assert _codigos(res) == ['P6'] and res['pagamentos'] == []


@precisa_amostras
def test_mesma_guia_duas_vezes(leitura_das):
    res = casamento.calcular([_doc(1, 'das.pdf', leitura_das), _doc(2, 'das (1).pdf', leitura_das)],
                             _empresa(leitura_das), [REGRA_DAS_SEM_CODIGO])
    assert _codigos(res) == ['P2', 'P7'] and len(res['pagamentos']) == 1


@precisa_amostras
def test_dois_debitos_iguais_sem_desempate_vira_ambiguidade(leitura_das):
    das = leitura_das['fatos'][0]

    def linha(fitid, memo):
        return {'tipo': 'extrato_linha', 'rotulo': 'Linha do extrato', 'data_efetiva': das['data_vencimento'],
                'valor_total': das['valor_total'], 'sentido': 'saida', 'historico': memo, 'fitid': fitid, 'conta': '99999'}
    extrato = {'reconhecido': True, 'origem': 'ofx', 'confianca': 1.0,
               'fatos': [linha('A', 'PAGAMENTO 1'), linha('B', 'PAGAMENTO 2')]}
    res = casamento.calcular([_doc(1, 'das.pdf', leitura_das), _doc(2, 'extrato.ofx', extrato)],
                             _empresa(leitura_das), [REGRA_DAS_SEM_CODIGO])
    assert 'P5' in _codigos(res)


def test_extrato_sem_regra_vira_pendencia_de_classificar():
    """Sem amostra real: só uma linha de extrato inventada."""
    linha = {'tipo': 'extrato_linha', 'rotulo': 'Linha do extrato', 'data_efetiva': date(2026, 3, 5),
             'valor_total': Decimal('49.90'), 'sentido': 'saida', 'historico': 'TARIFA', 'fitid': 'X1', 'conta': '1'}
    res = casamento.calcular([{'id': 1, 'nome': 'e.ofx', 'reconhecido': True, 'origem': 'ofx', 'confianca': 1.0,
                               'fatos': [linha]}], OUTRA_EMPRESA, [REGRA_DAS_SEM_CODIGO])
    assert _codigos(res) == ['P1'] and planilha.linhas(res['pagamentos']) == []
