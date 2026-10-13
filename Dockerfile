FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    RAG_DATA_DIR=/app/data \
    HF_HOME=/models/huggingface \
    FASTEMBED_CACHE_PATH=/models/fastembed

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --home-dir /app app \
    && mkdir -p /app/data /models/huggingface /models/fastembed \
    && chown -R app:app /app /models

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=app:app *.py ./
COPY --chown=app:app data/releases data/snapshots /app/data/

USER app
EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
  CMD python -c "import os,urllib.request; r=urllib.request.Request('http://127.0.0.1:8001/health/ready', headers={'x-rag-token':os.environ.get('RAG_SERVICE_TOKEN','')}); urllib.request.urlopen(r, timeout=5)" || exit 1

CMD ["uvicorn", "retrieval_service:app", "--host", "0.0.0.0", "--port", "8001"]
