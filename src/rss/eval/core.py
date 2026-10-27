import array
import json
import math
import statistics
import time
from pathlib import Path

import oracledb
import yaml

from rss import assistant, config, embeddings, search
from rss.pipeline.embed import embed

K = 10
CANDIDATES = 100
RRF_K = 60
MODELS = ["intfloat/e5-small-v2", "BAAI/bge-small-en-v1.5", "intfloat/multilingual-e5-small"]
QUERIES_FILE = Path(__file__).resolve().parents[3] / "eval" / "queries.yaml"


def load_queries() -> list[dict]:
    path = QUERIES_FILE if QUERIES_FILE.exists() else Path("/app/eval/queries.yaml")
    return yaml.safe_load(path.read_text())


def relevant_ids(conn: oracledb.Connection, rule: dict) -> set[str]:
    where, binds = [], {}
    if rule.get("categories"):
        names = ", ".join(f":cat{i}" for i in range(len(rule["categories"])))
        where.append(f"""EXISTS (SELECT 1 FROM cur_restaurant_category c
                         WHERE c.business_id = r.business_id AND c.category IN ({names}))""")
        binds |= {f"cat{i}": c for i, c in enumerate(rule["categories"])}
    for i, tag in enumerate(rule.get("tags", [])):
        where.append(f"EXISTS (SELECT 1 FROM cur_restaurant_tag t WHERE t.business_id = r.business_id AND t.tag = :tag{i})")
        binds[f"tag{i}"] = tag
    for feature in rule.get("features", []):
        if feature not in search.FEATURES:
            raise ValueError(f"unknown feature {feature}")
        where.append(f"r.{feature}")
    if "wifi" in rule:
        where.append("r.wifi = :wifi")
        binds["wifi"] = rule["wifi"]
    if "price_max" in rule:
        where.append("r.price_level <= :price_max")
        binds["price_max"] = rule["price_max"]
    if "price_min" in rule:
        where.append("r.price_level >= :price_min")
        binds["price_min"] = rule["price_min"]
    for i, m in enumerate(rule.get("mentions", [])):
        where.append(f"""r.business_id IN (SELECT v.business_id FROM stg_review v WHERE CONTAINS(v.review_text, :text{i}) > 0
                         GROUP BY v.business_id HAVING COUNT(*) >= :min{i})""")
        binds |= {f"text{i}": m["text"], f"min{i}": m["min"]}
    if "near" in rule:
        lat, lon = search.NEIGHBORHOODS[rule["near"]]
        where.append(f"SDO_WITHIN_DISTANCE(r.geom, {search.POINT}, :sdo_params) = 'TRUE'")
        binds |= {"lat": lat, "lon": lon, "sdo_params": f"distance={rule.get('radius_km', 1.0)} unit=KM"}
    with conn.cursor() as cur:
        cur.execute(f"SELECT r.business_id FROM cur_restaurant r WHERE {' AND '.join(where) or '1 = 1'}", binds)
        return {row[0] for row in cur}


def sync_text_index(conn: oracledb.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("BEGIN CTX_DDL.SYNC_INDEX('STG_REVIEW_TEXT_IX'); END;")


def ensure_embeddings(conn: oracledb.Connection, model: str) -> None:
    previous = config.EMBEDDING_MODEL
    config.EMBEDDING_MODEL = model
    try:
        embed(conn)
    finally:
        config.EMBEDDING_MODEL = previous


def rank_docs(conn: oracledb.Connection, qv: array.array, model: str, n: int) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT business_id FROM cur_restaurant_embedding WHERE model_name = :model
               ORDER BY VECTOR_DISTANCE(embedding, :qv, COSINE) FETCH FIRST :n ROWS ONLY""",
            model=model, qv=qv, n=n,
        )
        return [row[0] for row in cur]


def rank_passages(conn: oracledb.Connection, qv: array.array, model: str, n: int) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT business_id
               FROM (SELECT business_id, MIN(VECTOR_DISTANCE(embedding, :qv, COSINE)) AS distance
                     FROM cur_review_passage WHERE model_name = :model GROUP BY business_id)
               ORDER BY distance FETCH FIRST :n ROWS ONLY""",
            model=model, qv=qv, n=n,
        )
        return [row[0] for row in cur]


def rrf(*rankings: list[str]) -> list[str]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for position, business_id in enumerate(ranking, start=1):
            scores[business_id] = scores.get(business_id, 0) + 1 / (RRF_K + position)
    return sorted(scores, key=scores.get, reverse=True)


def retrieve(conn: oracledb.Connection, question: str, model: str, strategy: str, use_llm: str | None) -> list[str]:
    text, filters = question, None
    if use_llm:
        parsed = assistant.parse_question(conn, question)
        text = parsed["search_text"]
        filters = parsed["filters"] if use_llm == "filters" else None

    if filters:
        f = filters
        lat, lon = search.NEIGHBORHOODS[f["near"]] if f["near"] else (None, None)
        req = search.SearchRequest(
            text=text, price_max=f["price_max"], min_stars=f["min_stars"], category=f["category"], tags=f["tags"],
            features=f["features"], free_wifi=f["free_wifi"], lat=lat, lon=lon, radius_km=1.5, k=K, model=model,
        )
        return [r["business_id"] for r in search.search(conn, req)["results"]]

    if strategy == "app":
        return [r["business_id"] for r in search.search(conn, search.SearchRequest(text=text, k=K, model=model))["results"]]
    qv = array.array("f", embeddings.embed_query(text, model))
    if strategy == "doc":
        return rank_docs(conn, qv, model, K)
    if strategy == "passage":
        return rank_passages(conn, qv, model, K)
    if strategy == "hybrid":
        return rrf(rank_docs(conn, qv, model, CANDIDATES), rank_passages(conn, qv, model, CANDIDATES))[:K]
    raise ValueError(strategy)


def score(ranked: list[str], relevant: set[str]) -> dict:
    top = ranked[:K]
    hits = [i for i, b in enumerate(top, start=1) if b in relevant]
    ideal = min(K, len(relevant))
    dcg = sum(1 / math.log2(i + 1) for i in hits)
    idcg = sum(1 / math.log2(i + 1) for i in range(1, ideal + 1))
    return {
        "hits": len(hits),
        "precision": len(hits) / K,
        "recall": len(hits) / ideal if ideal else 0.0,
        "rr": 1 / hits[0] if hits else 0.0,
        "ndcg": dcg / idcg if idcg else 0.0,
    }


def run_search_experiment(conn, queries, labels, experiment, variant, model, strategy, use_llm=None) -> dict:
    rows = []
    for q in queries:
        t0 = time.perf_counter()
        ranked = retrieve(conn, q["question"], model, strategy, use_llm)
        latency = (time.perf_counter() - t0) * 1000
        rows.append({"query_id": q["id"], "relevant": len(labels[q["id"]]), "latency_ms": latency,
                     "top": ranked[:K], **score(ranked, labels[q["id"]])})
    summary = {
        "precision": statistics.mean(r["precision"] for r in rows),
        "recall": statistics.mean(r["recall"] for r in rows),
        "mrr": statistics.mean(r["rr"] for r in rows),
        "ndcg": statistics.mean(r["ndcg"] for r in rows),
        "p50_ms": statistics.median(r["latency_ms"] for r in rows),
    }
    with conn.cursor() as cur:
        run_id = cur.var(int)
        cur.execute(
            """INSERT INTO eval_run (experiment, variant, model, strategy, use_llm, k, queries,
                                     precision_at_k, recall_at_k, mrr, ndcg_at_k, p50_ms)
               VALUES (:1, :2, :3, :4, :5, :6, :7, :8, :9, :10, :11, :12) RETURNING run_id INTO :13""",
            [experiment, variant, model, strategy, bool(use_llm), K, len(rows), summary["precision"],
             summary["recall"], summary["mrr"], summary["ndcg"], summary["p50_ms"], run_id],
        )
        cur.executemany(
            """INSERT INTO eval_result (run_id, query_id, relevant_count, hits, precision_at_k, recall_at_k, rr,
                                        ndcg_at_k, latency_ms, details)
               VALUES (:1, :2, :3, :4, :5, :6, :7, :8, :9, JSON(:10))""",
            [(run_id.getvalue()[0], r["query_id"], r["relevant"], r["hits"], r["precision"], r["recall"], r["rr"],
              r["ndcg"], r["latency_ms"], json.dumps({"top": r["top"]})) for r in rows],
        )
    conn.commit()
    return {"experiment": experiment, "variant": variant, **summary, "rows": rows}


def _acceptable(expected, predicted) -> bool:
    if isinstance(expected, list):
        return predicted in expected
    return predicted == expected


def score_filters(expected: dict, optional: dict, predicted: dict) -> dict:
    invented, missed, wrong = [], [], []
    for field in ("price_max", "min_stars", "category", "near"):
        exp, got = expected.get(field), predicted.get(field)
        if exp is None:
            if got is not None:
                invented.append(f"{field}={got}")
        elif not _acceptable(exp, got):
            (missed if got is None else wrong).append(f"{field}={got}")
    for field in ("free_wifi", "open_now"):
        exp, got = bool(expected.get(field, False)), bool(predicted.get(field))
        if got and not exp:
            invented.append(field)
        elif exp and not got:
            missed.append(field)
    for field in ("tags", "features"):
        required = set(expected.get(field, []))
        allowed = required | set(optional.get(field, []))
        got = set(predicted.get(field, []))
        invented += [f"{field}:{v}" for v in sorted(got - allowed)]
        missed += [f"{field}:{v}" for v in sorted(required - got)]
    return {"correct": not (invented or missed or wrong), "invented": invented, "missed": missed, "wrong": wrong}


def run_llm_experiment(conn, queries) -> dict:
    rows = []
    for q in queries:
        t0 = time.perf_counter()
        parsed = assistant.parse_question(conn, q["question"])
        latency = (time.perf_counter() - t0) * 1000
        result = score_filters(q.get("expected_filters", {}), q.get("optional", {}), parsed["filters"])
        rows.append({"query_id": q["id"], "latency_ms": latency, "cache_hit": parsed["llm"]["cache_hit"],
                     "semantic_query": parsed["semantic_query"], **result})
    accuracy = statistics.mean(1.0 if r["correct"] else 0.0 for r in rows)
    invented = sum(len(r["invented"]) for r in rows)
    missed = sum(len(r["missed"]) + len(r["wrong"]) for r in rows)
    with conn.cursor() as cur:
        run_id = cur.var(int)
        cur.execute(
            """INSERT INTO eval_run (experiment, variant, model, strategy, use_llm, k, queries, filter_accuracy,
                                     invented_filters, missed_filters, p50_ms)
               VALUES ('C_filters', :1, :2, 'parse', TRUE, 0, :3, :4, :5, :6, :7) RETURNING run_id INTO :8""",
            [f"{config.LLM_PROVIDER}:{config.LLM_MODEL}:{assistant.PROMPT_VERSION}", config.LLM_MODEL, len(rows),
             accuracy, invented, missed, statistics.median(r["latency_ms"] for r in rows), run_id],
        )
        cur.executemany(
            """INSERT INTO eval_result (run_id, query_id, relevant_count, hits, latency_ms, details)
               VALUES (:1, :2, 0, :3, :4, JSON(:5))""",
            [(run_id.getvalue()[0], r["query_id"], int(r["correct"]), r["latency_ms"],
              json.dumps({k: r[k] for k in ("semantic_query", "invented", "missed", "wrong", "cache_hit")}))
             for r in rows],
        )
    conn.commit()
    return {"accuracy": accuracy, "invented": invented, "missed": missed, "rows": rows}
