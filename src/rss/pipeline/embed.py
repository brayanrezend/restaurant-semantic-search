import array
import time

import oracledb

from rss import config, embeddings

BATCH_SIZE = 64


def embed(conn: oracledb.Connection) -> None:
    model = config.EMBEDDING_MODEL
    revision = embeddings.model_revision(model)
    with conn.cursor() as cur:
        cur.execute(
            """SELECT d.business_id, d.doc_text, d.doc_hash
               FROM cur_restaurant_doc d
               LEFT JOIN cur_restaurant_embedding e ON e.business_id = d.business_id AND e.model_name = :model
               WHERE e.business_id IS NULL OR e.doc_hash <> d.doc_hash OR e.model_revision <> :revision""",
            model=model, revision=revision,
        )
        pending = cur.fetchall()
        cur.execute("SELECT COUNT(*) FROM cur_restaurant_doc")
        total = cur.fetchone()[0]
    print(f"  model {model}@{revision[:10]}: {len(pending):,} of {total:,} docs to embed")
    if not pending:
        return

    t0 = time.time()
    with conn.cursor() as cur:
        for i in range(0, len(pending), BATCH_SIZE):
            batch = pending[i:i + BATCH_SIZE]
            vectors = embeddings.embed_passages([text for _, text, _ in batch], model)
            cur.executemany(
                """MERGE INTO cur_restaurant_embedding t
                   USING (SELECT :1 AS business_id, :2 AS model_name, :3 AS model_revision, :4 AS doc_hash,
                                 :5 AS embedding FROM dual) s
                   ON (t.business_id = s.business_id AND t.model_name = s.model_name)
                   WHEN MATCHED THEN UPDATE SET t.model_revision = s.model_revision, t.doc_hash = s.doc_hash,
                        t.embedding = s.embedding, t.embedded_at = SYSTIMESTAMP
                   WHEN NOT MATCHED THEN INSERT (business_id, model_name, model_revision, doc_hash, embedding)
                        VALUES (s.business_id, s.model_name, s.model_revision, s.doc_hash, s.embedding)""",
                [(bid, model, revision, doc_hash, array.array("f", v)) for (bid, _, doc_hash), v in zip(batch, vectors)],
            )
            conn.commit()
            print(f"  embedded {min(i + BATCH_SIZE, len(pending)):,}/{len(pending):,}")
    print(f"  {len(pending) / (time.time() - t0):.1f} docs/s")
