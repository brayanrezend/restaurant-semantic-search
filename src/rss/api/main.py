import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import oracledb
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from rss import assistant, embeddings, llm, search
from rss.db import create_pool

STATIC = Path(__file__).parent / "static"
state: dict = {"llm_status": None, "llm_checked": 0.0}


@asynccontextmanager
async def lifespan(app: FastAPI):
    state["pool"] = create_pool()
    embeddings.embed_query("warm up")
    threading.Thread(target=_warm_llm, daemon=True).start()
    yield
    state["pool"].close()


def _warm_llm() -> None:
    try:
        llm.warm_up()
    except Exception as e:
        print(f"LLM warm-up skipped: {e}")


def llm_status() -> dict:
    if time.time() - state["llm_checked"] > 30:
        state["llm_status"], state["llm_checked"] = llm.status(), time.time()
    return state["llm_status"]


app = FastAPI(title="restaurant-semantic-search", lifespan=lifespan)


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/health")
def health():
    with state["pool"].acquire() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM cur_restaurant_embedding")
        return {"status": "ok", "embeddings": cur.fetchone()[0], "llm": llm_status()}


@app.get("/api/search")
def api_search(
    q: str = "",
    price_max: int | None = Query(None, ge=1, le=4),
    min_stars: float | None = Query(None, ge=1, le=5),
    category: str | None = None,
    tag: list[str] = Query([]),
    feature: list[str] = Query([]),
    free_wifi: bool = False,
    open_now: bool = False,
    at: datetime | None = None,
    lat: float | None = None,
    lon: float | None = None,
    radius_km: float = Query(2.0, gt=0, le=30),
    k: int = Query(10, ge=1, le=50),
):
    req = search.SearchRequest(
        text=q, price_max=price_max, min_stars=min_stars, category=category, tags=tag, features=feature,
        free_wifi=free_wifi, open_now=open_now, at=at, lat=lat, lon=lon, radius_km=radius_km, k=k,
    )
    try:
        with state["pool"].acquire() as conn:
            return search.search(conn, req)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    except oracledb.DatabaseError as e:
        raise HTTPException(503, f"database error: {e}; did you run 'make pipeline'?") from e


@app.get("/api/restaurants/{business_id}")
def api_restaurant(business_id: str):
    with state["pool"].acquire() as conn:
        restaurant = search.get_restaurant(conn, business_id)
    if not restaurant:
        raise HTTPException(404, "restaurant not found")
    return restaurant


@app.get("/api/facets")
def api_facets():
    with state["pool"].acquire() as conn:
        return search.facets(conn)


class ParseRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class ExplainRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    query: str = Field("", max_length=500)
    business_ids: list[str] = Field(min_length=1, max_length=10)


def _require_llm() -> None:
    status = llm_status()
    if not status["enabled"]:
        raise HTTPException(503, f"LLM disabled: {status['reason']}")


@app.post("/api/assistant/parse")
def api_parse(body: ParseRequest):
    _require_llm()
    try:
        with state["pool"].acquire() as conn:
            return assistant.parse_question(conn, body.question)
    except llm.LLMError as e:
        raise HTTPException(502, str(e)) from e


@app.post("/api/assistant/explain")
def api_explain(body: ExplainRequest):
    _require_llm()
    try:
        with state["pool"].acquire() as conn:
            return assistant.explain_results(conn, body.question, body.query, body.business_ids)
    except llm.LLMError as e:
        raise HTTPException(502, str(e)) from e
