import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

import oracledb

from rss import config

oracledb.defaults.fetch_lobs = False

PLSQL_START = re.compile(r"^\s*(CREATE\s+(OR\s+REPLACE\s+)?(FUNCTION|PROCEDURE|PACKAGE|TRIGGER|TYPE)\b|BEGIN\b|DECLARE\b)", re.I)

T = TypeVar("T")


def _retry(fn: Callable[[], T], attempts: int = 60, delay: float = 5) -> T:
    for i in range(1, attempts + 1):
        try:
            return fn()
        except oracledb.Error as e:
            if i == attempts:
                raise
            print(f"waiting for Oracle ({i}/{attempts}): {e}")
            time.sleep(delay)


def connect() -> oracledb.Connection:
    return _retry(lambda: oracledb.connect(user=config.DB_USER, password=config.DB_PASSWORD, dsn=config.DB_DSN))


def create_pool() -> oracledb.ConnectionPool:
    def attempt():
        pool = oracledb.create_pool(user=config.DB_USER, password=config.DB_PASSWORD, dsn=config.DB_DSN, min=1, max=4)
        with pool.acquire() as conn:
            conn.ping()
        return pool

    return _retry(attempt)


def split_sql(text: str) -> list[str]:
    statements, buf = [], []
    for line in text.splitlines():
        if line.strip().startswith("--"):
            continue
        if line.strip() == "/":
            statements.append("\n".join(buf).strip())
            buf = []
            continue
        buf.append(line)
        current = "\n".join(buf)
        if line.rstrip().endswith(";") and not PLSQL_START.match(current):
            statements.append(current.strip().rstrip(";"))
            buf = []
    statements.append("\n".join(buf).strip())
    return [s for s in statements if s]


def run_sql_file(conn: oracledb.Connection, path: Path) -> None:
    with conn.cursor() as cur:
        for statement in split_sql(path.read_text()):
            cur.execute(statement)
            print(f"  {path.name}: {statement.split()[0].upper()} {cur.rowcount if cur.rowcount >= 0 else ''}".rstrip())
    conn.commit()
