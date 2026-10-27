import re

import oracledb

from rss import config
from rss.db import split_sql

CHECK_HEADER = re.compile(r":run_id,\s*'(\w+)',\s*'(ERROR|WARN|INFO)'")


def run_checks(conn: oracledb.Connection) -> None:
    with conn.cursor() as cur:
        run_id = cur.var(int)
        cur.execute("INSERT INTO dq_run (status) VALUES ('RUNNING') RETURNING run_id INTO :1", [run_id])
        run_id = run_id.getvalue()[0]
        conn.commit()
        try:
            for statement in split_sql((config.DB_DIR / "quality" / "checks.sql").read_text()):
                name, severity = CHECK_HEADER.search(statement).groups()
                cur.execute(statement, run_id=run_id)
                failed = cur.rowcount
                cur.execute(
                    "INSERT INTO dq_check (run_id, check_name, severity, failed_rows) VALUES (:1, :2, :3, :4)",
                    [run_id, name, severity, failed],
                )
                print(f"  {severity:5} {name:30} {failed:>7,}")
            cur.execute("UPDATE dq_run SET status = 'SUCCESS', finished_at = SYSTIMESTAMP WHERE run_id = :1", [run_id])
            conn.commit()
        except Exception:
            conn.rollback()
            cur.execute("UPDATE dq_run SET status = 'FAILED', finished_at = SYSTIMESTAMP WHERE run_id = :1", [run_id])
            conn.commit()
            raise
