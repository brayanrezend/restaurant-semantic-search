import hashlib
import json
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import oracledb

from rss import config

BATCH_SIZE = 5000
RAW_TABLES = {"business": "raw_business", "review": "raw_review"}


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _start_batch(cur: oracledb.Cursor, source: str, path: Path, sha: str, extract_filter: str | None) -> int | None:
    cur.execute(
        """SELECT batch_id FROM etl_batch
           WHERE source_name = :1 AND file_sha256 = :2 AND NVL(extract_filter, '-') = NVL(:3, '-')
             AND status = 'SUCCESS'""",
        [source, sha, extract_filter],
    )
    if cur.fetchone():
        return None
    table = RAW_TABLES[source]
    cur.execute(
        f"DELETE FROM {table} WHERE batch_id IN (SELECT batch_id FROM etl_batch WHERE source_name = :1 AND status <> 'SUCCESS')",
        [source],
    )
    batch_id = cur.var(int)
    cur.execute(
        """INSERT INTO etl_batch (source_name, source_file, file_sha256, extract_filter, status)
           VALUES (:1, :2, :3, :4, 'RUNNING') RETURNING batch_id INTO :5""",
        [source, path.name, sha, extract_filter, batch_id],
    )
    cur.connection.commit()
    return batch_id.getvalue()[0]


def load_jsonl(
    conn: oracledb.Connection,
    source: str,
    path: Path,
    keep: Callable[[str], bool] = lambda line: True,
    extract_filter: str | None = None,
) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{path} not found; see 'Getting the data' in the README")
    t0 = time.time()
    print(f"  hashing {path.name} ...")
    sha = file_sha256(path)
    table = RAW_TABLES[source]

    with conn.cursor() as cur:
        batch_id = _start_batch(cur, source, path, sha, extract_filter)
        if batch_id is None:
            print(f"  {source}: file unchanged and already loaded, skipping")
            return
        try:
            cur.setinputsizes(None, None, oracledb.DB_TYPE_JSON)
            rows_read = rows_loaded = 0
            for chunk, read in _chunks(path, keep, batch_id):
                if chunk:
                    cur.executemany(f"INSERT INTO {table} (batch_id, line_no, doc) VALUES (:1, :2, :3)", chunk)
                    conn.commit()
                if read // 1_000_000 > rows_read // 1_000_000:
                    print(f"  {source}: read {read:,} lines, loaded {rows_loaded + len(chunk):,}")
                rows_read, rows_loaded = read, rows_loaded + len(chunk)
            cur.execute(
                f"""DELETE FROM {table}
                    WHERE batch_id IN (SELECT batch_id FROM etl_batch WHERE source_name = :1 AND batch_id <> :2)""",
                [source, batch_id],
            )
            cur.execute(
                """UPDATE etl_batch SET status = 'SUCCESS', rows_read = :1, rows_loaded = :2, finished_at = SYSTIMESTAMP
                   WHERE batch_id = :3""",
                [rows_read, rows_loaded, batch_id],
            )
            conn.commit()
            print(f"  {source}: batch {batch_id} loaded {rows_loaded:,} of {rows_read:,} lines in {time.time() - t0:.0f}s")
        except Exception as e:
            conn.rollback()
            cur.execute(
                "UPDATE etl_batch SET status = 'FAILED', error_message = :1, finished_at = SYSTIMESTAMP WHERE batch_id = :2",
                [str(e)[:4000], batch_id],
            )
            conn.commit()
            raise


def _chunks(path: Path, keep: Callable[[str], bool], batch_id: int) -> Iterator[tuple[list, int]]:
    chunk = []
    line_no = 0
    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            if keep(line):
                chunk.append((batch_id, line_no, json.loads(line)))
                if len(chunk) >= BATCH_SIZE:
                    yield chunk, line_no
                    chunk = []
    yield chunk, line_no


def load_business(conn: oracledb.Connection) -> None:
    load_jsonl(conn, "business", config.BUSINESS_FILE)


def _business_id(line: str) -> str | None:
    i = line.find('"business_id":"')
    if i < 0:
        return json.loads(line).get("business_id")
    start = i + len('"business_id":"')
    return line[start:line.index('"', start)]


def load_reviews(conn: oracledb.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT business_id FROM v_business_scope ORDER BY business_id")
        ids = [r[0] for r in cur.fetchall()]
    if not ids:
        raise RuntimeError("v_business_scope is empty; run load-business and stg-business first")
    scope = set(ids)
    extract_filter = f"v_business_scope n={len(ids)} sha={hashlib.sha256(','.join(ids).encode()).hexdigest()[:16]}"
    print(f"  review scope: {len(ids):,} businesses")
    load_jsonl(conn, "review", config.REVIEW_FILE, lambda line: _business_id(line) in scope, extract_filter)
