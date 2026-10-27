FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    HF_HOME=/app/.hf

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --default-timeout=120 --retries 5 \
      --index-url https://download.pytorch.org/whl/cpu torch==2.6.0

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --default-timeout=120 --retries 5 -r requirements.txt

ARG EMBEDDING_MODELS=intfloat/e5-small-v2,BAAI/bge-small-en-v1.5,intfloat/multilingual-e5-small
RUN python -c "import sys; from sentence_transformers import SentenceTransformer; [SentenceTransformer(m) for m in sys.argv[1].split(',')]" "${EMBEDDING_MODELS}"
ENV HF_HUB_OFFLINE=1 \
    EMBEDDING_MODEL=intfloat/multilingual-e5-small

COPY src ./src
COPY db ./db
