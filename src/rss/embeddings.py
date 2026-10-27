from functools import lru_cache
from pathlib import Path

from rss import config

PREFIXES = {
    "intfloat/e5-small-v2": ("query: ", "passage: "),
    "intfloat/multilingual-e5-small": ("query: ", "passage: "),
    "BAAI/bge-small-en-v1.5": ("Represent this sentence for searching relevant passages: ", ""),
}


@lru_cache
def _model(name: str):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(name)


@lru_cache
def model_revision(name: str | None = None) -> str:
    from huggingface_hub import snapshot_download

    return Path(snapshot_download(name or config.EMBEDDING_MODEL, local_files_only=True)).name


def embed_passages(texts: list[str], model: str | None = None) -> list[list[float]]:
    model = model or config.EMBEDDING_MODEL
    prefix = PREFIXES.get(model, ("", ""))[1]
    return _model(model).encode([prefix + t for t in texts], batch_size=32, normalize_embeddings=True).tolist()


def embed_query(text: str, model: str | None = None) -> list[float]:
    model = model or config.EMBEDDING_MODEL
    prefix = PREFIXES.get(model, ("", ""))[0]
    return _model(model).encode(prefix + text, normalize_embeddings=True).tolist()
