FROM python:3.13-slim

WORKDIR /app

# Tesseract (só o binário: o modelo de português vai no projeto, em tessdata/, para o OCR do
# servidor ser o mesmo que foi testado) + libpq + fuso.
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libpq5 \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

ENV TZ=America/Sao_Paulo

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Usuário não-root; a pasta dos documentos já nasce dele (o volume herda o dono).
RUN useradd -m -u 1000 appuser && mkdir -p /data/docs && chown -R appuser:appuser /app /data
USER appuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    FLASK_ENV=production \
    TESSDATA_DIR=/app/tessdata \
    DOCS_DIR=/data/docs \
    PORT=5000

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:5000/health', timeout=3).status==200 else 1)"

# init_db é idempotente: roda a cada subida (cria/migra o banco, semeia admin e a regra do DAS)
# e só então sobe o servidor. Dispensa o `docker exec … init_db.py` a cada deploy.
CMD ["sh", "-c", "python -X utf8 init_db.py && exec python -X utf8 server.py"]
