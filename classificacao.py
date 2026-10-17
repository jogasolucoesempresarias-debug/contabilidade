"""Regras → lançamento automático, histórico e complemento (MAPEAMENTO §7).

As regras são DADO (tabela `regras`), não código: refinar uma regra é editar a tabela (D6).
Ordem: regra da empresa antes da geral; entre iguais, a mais antiga (menor id).
"""
import re

from leitura.util import normalizar_nome, so_digitos


def _competencia_do_comprovante(descricao):
    """'DAS 09.26' → '09/2026'."""
    m = re.search(r'(\d{2})[./](\d{2,4})', descricao or '')
    if not m:
        return ''
    ano = m.group(2)
    return f'{m.group(1)}/{"20" + ano if len(ano) == 2 else ano}'


def contexto(pag):
    g, c, e = pag.get('_guia'), pag.get('_comprovante'), pag.get('_extrato')
    return {
        'competencia': (g or {}).get('competencia') or _competencia_do_comprovante((c or {}).get('descricao')),
        'numero': (g or {}).get('numero_documento') or '',
        'historico': (e or {}).get('historico') or '',
        'contraparte': (g or {}).get('contraparte_nome') or (c or {}).get('convenio') or '',
        'rotulo': pag.get('descricao') or '',
    }


def _casa(regra, pag):
    g, c, e = pag.get('_guia'), pag.get('_comprovante'), pag.get('_extrato')
    gatilho, valor = regra['gatilho'], (regra['valor'] or '').strip()
    if gatilho == 'tipo_doc':
        return valor.upper() in {((g or {}).get('subtipo') or '').upper(), ((c or {}).get('convenio') or '').upper()} - {''}
    if gatilho == 'historico_contem':
        alvo = ' '.join(normalizar_nome(valor))
        return bool(e) and bool(alvo) and alvo in ' '.join(normalizar_nome(e.get('historico')))
    if gatilho == 'cnpj':
        cnpj = so_digitos((g or {}).get('contraparte_cnpj') or '')
        return bool(cnpj) and cnpj == so_digitos(valor)
    return False


def montar_complemento(modelo, ctx):
    texto = (modelo or '{rotulo}').format_map({k: ctx.get(k, '') for k in ('competencia', 'numero', 'historico', 'contraparte', 'rotulo')})
    texto = re.sub(r'\s+Nº\s*$', '', texto)          # sem número, não deixa "Nº" pendurado
    return re.sub(r'\s{2,}', ' ', texto).strip()[:200]


def classificar(pag, regras, empresa_id):
    ordenadas = sorted((r for r in regras if r.get('ativa', True)),
                       key=lambda r: (r.get('empresa_id') is None, r['id']))
    for r in ordenadas:
        if r.get('empresa_id') not in (None, empresa_id):
            continue
        if _casa(r, pag):
            return {'regra_id': r['id'], 'regra': r.get('descricao') or r['valor'],
                    'lancto_auto': (r.get('lancto_auto') or '').strip(),
                    'debito': r.get('conta_debito'), 'credito': r.get('conta_credito'),
                    'cod_historico': r.get('cod_historico'),
                    'complemento': montar_complemento(r.get('modelo_complemento'), contexto(pag))}
    return None
