import array
import statistics
import time

import oracledb

from rss import config, embeddings

TARGETS = [70, 80, 90, 95, 99]
K = 10
REPEATS = 5

EXACT_SQL = """SELECT review_id || ':' || passage_no FROM cur_review_passage
ORDER BY VECTOR_DISTANCE(embedding, :qv, COSINE)
FETCH EXACT FIRST {k} ROWS ONLY"""

APPROX_SQL = """SELECT review_id || ':' || passage_no FROM cur_review_passage
ORDER BY VECTOR_DISTANCE(embedding, :qv, COSINE)
FETCH APPROX FIRST {k} ROWS ONLY WITH TARGET ACCURACY {target}"""


def _timed(cur: oracledb.Cursor, sql: str, qv: array.array) -> tuple[list[str], float]:
    samples, rows = [], []
    cur.execute(sql, qv=qv)
    cur.fetchall()
    for _ in range(REPEATS):
        t0 = time.perf_counter()
        cur.execute(sql, qv=qv)
        rows = [r[0] for r in cur.fetchall()]
        samples.append((time.perf_counter() - t0) * 1000)
    return rows, statistics.median(samples)


def _plan(cur: oracledb.Cursor, sql: str, qv: array.array) -> str:
    cur.execute("DELETE FROM plan_table")
    cur.execute("EXPLAIN PLAN FOR " + sql, qv=qv)
    cur.execute("""SELECT LISTAGG(operation || ' ' || options, ', ') WITHIN GROUP (ORDER BY id)
                   FROM plan_table WHERE operation LIKE 'VECTOR%' OR options LIKE '%VECTOR%'""")
    return cur.fetchone()[0] or "no vector index operation in plan"


def _p95(values: list[float]) -> float:
    return sorted(values)[max(0, round(0.95 * len(values)) - 1)]


def run_ann_benchmark(conn: oracledb.Connection, questions: list[str]) -> list[dict]:
    model = config.EMBEDDING_MODEL
    vectors = [array.array("f", embeddings.embed_query(q, model)) for q in questions]
    results = []
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM cur_review_passage")
        total = cur.fetchone()[0]
        exact = [_timed(cur, EXACT_SQL.format(k=K), v) for v in vectors]
        exact_ms = [ms for _, ms in exact]
        for target in TARGETS:
            sql = APPROX_SQL.format(k=K, target=target)
            approx = [_timed(cur, sql, v) for v in vectors]
            recall = statistics.mean(len(set(a) & set(e)) / K for (a, _), (e, _) in zip(approx, exact))
            approx_ms = [ms for _, ms in approx]
            row = {
                "target": target, "recall": recall, "vectors": total,
                "exact_p50": statistics.median(exact_ms), "exact_p95": _p95(exact_ms),
                "approx_p50": statistics.median(approx_ms), "approx_p95": _p95(approx_ms),
                "plan": _plan(cur, sql, vectors[0]),
            }
            results.append(row)
            cur.execute(
                """INSERT INTO ann_benchmark (table_name, vectors, target_accuracy, k, queries, recall_vs_exact,
                                              exact_p50_ms, exact_p95_ms, approx_p50_ms, approx_p95_ms, approx_plan)
                   VALUES ('cur_review_passage', :1, :2, :3, :4, :5, :6, :7, :8, :9, :10)""",
                [total, target, K, len(vectors), recall, row["exact_p50"], row["exact_p95"],
                 row["approx_p50"], row["approx_p95"], row["plan"][:200]],
            )
    conn.commit()
    return results
