import os
from pathlib import Path

DB_USER = os.getenv("DB_USER", "rss_app")
DB_PASSWORD = os.getenv("DB_PASSWORD", "rss_app")
DB_DSN = os.getenv("DB_DSN", "localhost:1521/FREEPDB1")

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-small")

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")
LLM_MODEL = os.getenv("LLM_MODEL") or {"ollama": "qwen2.5:7b", "anthropic": "claude-opus-5-5"}.get(LLM_PROVIDER, "")
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "60"))
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")

DATA_DIR = Path(os.getenv("DATA_DIR", "data/raw"))
DB_DIR = Path(os.getenv("DB_DIR", "db"))

BUSINESS_FILE = DATA_DIR / "yelp_academic_dataset_business.json"
REVIEW_FILE = DATA_DIR / "yelp_academic_dataset_review.json"
