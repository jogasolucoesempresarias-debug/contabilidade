"""Porta de entrada: identifica o formato pelo CONTEÚDO (não pela extensão) e recusa imagem.

Fase 1 aceita só PDF, OFX e XML (decisão D5 do PLANO). Foto de câmera derruba a leitura.
"""
import hashlib

MSG_IMAGEM = 'Este arquivo é uma imagem. Envie o PDF do documento (o original do banco ou do emissor).'
MSG_FORMATO = 'Formato não aceito. Envie PDF, OFX ou XML.'
MSG_VAZIO = 'Arquivo vazio.'


class ArquivoRecusado(Exception):
    pass


def _eh_imagem(c):
    return (c[:3] == b'\xff\xd8\xff'                      # JPEG
            or c[:8] == b'\x89PNG\r\n\x1a\n'              # PNG
            or c[:6] in (b'GIF87a', b'GIF89a')
            or (c[:4] == b'RIFF' and c[8:12] == b'WEBP')
            or c[:4] in (b'II*\x00', b'MM\x00*')           # TIFF
            or c[:2] == b'BM'                             # BMP
            or (c[4:8] == b'ftyp' and c[8:12] in (b'heic', b'heix', b'hevc', b'heim', b'heis',
                                                  b'mif1', b'msf1', b'avif')))   # HEIC/AVIF do celular


def identificar(conteudo):
    """'pdf' | 'ofx' | 'xml', ou ArquivoRecusado com a mensagem para quem enviou."""
    if not conteudo:
        raise ArquivoRecusado(MSG_VAZIO)
    if _eh_imagem(conteudo):
        raise ArquivoRecusado(MSG_IMAGEM)
    inicio = conteudo[:2048].lstrip(b'\xef\xbb\xbf \t\r\n')
    if inicio[:5] == b'%PDF-' or b'%PDF-' in conteudo[:1024]:
        return 'pdf'
    cabeca = conteudo[:4096].upper()
    if b'OFXHEADER' in cabeca or b'<OFX>' in cabeca:
        return 'ofx'
    if inicio[:1] == b'<':
        return 'xml'
    raise ArquivoRecusado(MSG_FORMATO)


def sha256(conteudo):
    return hashlib.sha256(conteudo).hexdigest()
