"""Leitura de um arquivo enviado → fatos (o formato comum do MAPEAMENTO §4).

Ordem: formato pelo conteúdo → OFX/XML/PDF → PDF com texto tenta os leitores de texto; PDF sem
texto passa no OCR e tenta os leitores de imagem. Documento sem leitor fica como "não
reconhecido nesta versão" — nunca com dado inventado.
"""
from . import boleto, comprovante_sicoob, das, entrada, ofx, pdf
from .entrada import ArquivoRecusado  # noqa: F401  (reexportado para o servidor)

CONFIANCA_MINIMA_OCR = 0.80


def ler_arquivo(conteudo):
    """Devolve dict com formato, tipo, reconhecido, origem, confianca, fatos, avisos, texto, resumo."""
    formato = entrada.identificar(conteudo)
    r = {'formato': formato, 'tipo': None, 'reconhecido': False, 'origem': None,
         'confianca': None, 'fatos': [], 'avisos': [], 'texto': '', 'resumo': None}

    if formato == 'ofx':
        linhas, resumo, avisos = ofx.ler(conteudo)
        r.update(tipo='Extrato OFX', reconhecido=bool(linhas), origem='ofx', confianca=1.0,
                 fatos=linhas, avisos=avisos, resumo={k: (str(v) if v is not None else None) for k, v in resumo.items()})
        return r

    if formato == 'xml':
        r.update(origem='xml', avisos=['XML ainda não é lido nesta versão (nota fiscal entra no mapeamento)'])
        return r

    lido = pdf.ler_texto(conteudo)
    if lido['tem_texto']:
        r.update(origem='texto', confianca=1.0, texto=lido['texto'])
        fato = das.ler(lido['texto'], lido['palavras'][0] if lido['palavras'] else [])
        if not fato:
            fato = boleto.ler(lido['texto'])
        if fato:
            r.update(tipo=fato['rotulo'], reconhecido=True, fatos=[fato], avisos=list(fato.get('avisos', [])))
        return r

    ocr = pdf.ler_ocr(conteudo)
    r.update(origem='ocr', confianca=ocr['confianca'], texto=ocr['texto'])
    fato = comprovante_sicoob.ler(ocr['texto'])
    if fato:
        r.update(tipo=fato['rotulo'], reconhecido=True, fatos=[fato], avisos=list(fato.get('avisos', [])))
    if ocr['confianca'] < CONFIANCA_MINIMA_OCR:
        r['avisos'].append(f'Leitura com baixa confiança ({ocr["confianca"]:.0%}). '
                           'Se for foto ou digitalização, envie o PDF original do banco ou do emissor.')
    return r
