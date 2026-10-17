"""PDF → texto. Com camada de texto, lê direto (pdfplumber). Sem texto (PDF que é uma imagem,
como o comprovante do Sicoob gerado pelo iPhone), renderiza a página e passa no Tesseract.

PyMuPDF não é usado de propósito: é AGPL (ver PLANO.md §4.3).
"""
import io
import os
import shutil

import pdfplumber

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# O modelo de português (tessdata_best) vai junto no projeto, para o OCR do servidor ser o mesmo
# que foi testado aqui. O pacote do Debian traz outro modelo.
TESSDATA_DIR = os.getenv('TESSDATA_DIR') or os.path.join(BASE_DIR, 'tessdata')
MIN_CARACTERES_TEXTO = 40      # abaixo disso a página é tratada como imagem
MAX_PAGINAS_OCR = 4
LARGURA_OCR_PX = 2480          # ~300 dpi numa folha A4


def _tesseract_cmd():
    cmd = os.getenv('TESSERACT_CMD')
    if cmd:
        return cmd
    if shutil.which('tesseract'):
        return 'tesseract'
    windows = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    return windows if os.path.exists(windows) else 'tesseract'


def ler_texto(conteudo):
    """Texto e palavras com posição de cada página. `tem_texto` diz se vale ler sem OCR."""
    paginas, palavras = [], []
    with pdfplumber.open(io.BytesIO(conteudo)) as pdf:
        for p in pdf.pages:
            paginas.append(p.extract_text() or '')
            palavras.append(p.extract_words(keep_blank_chars=False))
    texto = '\n'.join(paginas)
    return {'texto': texto, 'paginas': len(paginas), 'palavras': palavras,
            'tem_texto': len(texto.strip()) >= MIN_CARACTERES_TEXTO}


def ler_ocr(conteudo):
    """OCR das primeiras páginas. Devolve o texto em linhas e a confiança média (0–1)."""
    import pypdfium2
    import pytesseract

    pytesseract.pytesseract.tesseract_cmd = _tesseract_cmd()
    os.environ['TESSDATA_PREFIX'] = TESSDATA_DIR
    doc = pypdfium2.PdfDocument(conteudo)
    linhas, confs = [], []
    try:
        for i in range(min(len(doc), MAX_PAGINAS_OCR)):
            pagina = doc[i]
            largura, _ = pagina.get_size()
            escala = min(5.0, max(1.0, LARGURA_OCR_PX / largura))
            imagem = pagina.render(scale=escala).to_pil()
            dados = pytesseract.image_to_data(imagem, lang='por', config='--psm 4',
                                              output_type=pytesseract.Output.DICT)
            atual, chave_atual = [], None
            for j, palavra in enumerate(dados['text']):
                conf = float(dados['conf'][j])
                if conf < 0 or not palavra.strip():
                    continue
                chave = (dados['block_num'][j], dados['par_num'][j], dados['line_num'][j])
                if chave != chave_atual and atual:
                    linhas.append(' '.join(atual))
                    atual = []
                chave_atual = chave
                atual.append(palavra)
                confs.append(conf)
            if atual:
                linhas.append(' '.join(atual))
    finally:
        doc.close()
    confianca = round(sum(confs) / len(confs) / 100, 3) if confs else 0.0
    return {'texto': '\n'.join(linhas), 'confianca': confianca}
