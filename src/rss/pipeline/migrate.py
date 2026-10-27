import hashlib

import oracledb

from rss import config
from rss.db import split_sql


def migrate(conn: oracledb.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
              version    VARCHAR2(200) PRIMARY KEY,
              checksum   VARCHAR2(64)  NOT NULL,
              applied_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
            )""")
        cur.execute("SELECT version, checksum FROM schema_migrations")
        applied = dict(cur.fetchall())

        folder = config.DB_DIR / "migrations"
        for path in [*sorted(folder.glob("V*.sql")), *sorted(folder.glob("R__*.sql"))]:
            text = path.read_text()
            checksum = hashlib.sha256(text.encode()).hexdigest()
            if applied.get(path.name) == checksum:
                continue
            if path.name in applied and not path.name.startswith("R__"):
                raise RuntimeError(f"{path.name} was modified after being applied; add a new migration instead")
            for statement in split_sql(text):
                cur.execute(statement)
                if cur.warning:
                    raise RuntimeError(f"{path.name}: {cur.warning}\n{statement[:200]}")
            cur.execute(
                """MERGE INTO schema_migrations t USING (SELECT :1 AS version, :2 AS checksum FROM dual) s
                   ON (t.version = s.version)
                   WHEN MATCHED THEN UPDATE SET t.checksum = s.checksum, t.applied_at = SYSTIMESTAMP
                   WHEN NOT MATCHED THEN INSERT (version, checksum) VALUES (s.version, s.checksum)""",
                [path.name, checksum],
            )
            conn.commit()
            print(f"  applied {path.name}")
    print("  schema up to date")
