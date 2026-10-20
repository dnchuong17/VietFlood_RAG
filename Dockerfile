FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    RAG_DATA_DIR=/app/data \
    RAG_SOURCE_DIR=/app/data/sources \
    HF_HOME=/models/huggingface \
    FASTEMBED_CACHE_PATH=/models/fastembed

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --home-dir /app app \
    && mkdir -p /app/data /app/bootstrap /models/huggingface /models/fastembed \
    && chown -R app:app /app /models

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=app:app *.py ./
COPY --chown=app:app portal.html portal.js upload-template.md source_registry.jsonl ./
COPY --chown=app:app rag_sources/markdown/ ./rag_sources/markdown/
# Keep image seeds outside the writable volume so later deployments can add artifacts.
COPY --chown=app:app data/releases/ /app/bootstrap/releases/
COPY --chown=app:app data/snapshots/ /app/bootstrap/snapshots/

USER app
EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=15s --start-period=300s --retries=3 \
  CMD python -c "import os,urllib.request; r=urllib.request.Request('http://127.0.0.1:8001/health/ready', headers={'x-rag-token':os.environ.get('RAG_SERVICE_TOKEN','')}); urllib.request.urlopen(r, timeout=10)" || exit 1

ENTRYPOINT ["python", "/app/container_entrypoint.py"]
CMD ["uvicorn", "retrieval_service:app", "--host", "0.0.0.0", "--port", "8001"]
