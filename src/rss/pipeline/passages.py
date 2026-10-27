import array
import re
import time

import oracledb

from rss import config, embeddings

MIN_CHARS = 40
MAX_CHARS = 300
BATCH_SIZE = 256


def split_passages(text: str) -> list[str]:
    passages = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
        sentence = " ".join(sentence.split())
        if len(sentence) < MIN_CHARS:
            continue
        if len(sentence) > MAX_CHARS:
            sentence = sentence[:MAX_CHARS].rsplit(" ", 1)[0] + "…"
        passages.append(sentence)
    return passages


def embed_passages(conn: oracledb.Connection) -> None:
    model = config.EMBEDDING_MODEL
    revision = embeddings.model_revision(model)
    with conn.cursor() as cur:
        cur.execute(
            """DELETE FROM cur_review_passage p
               WHERE p.model_name = :model
                 AND (p.model_revision <> :revision OR NOT EXISTS (
                   SELECT 1 FROM cur_restaurant_doc d,
                          JSON_TABLE(d.review_ids, '$[*]' COLUMNS (review_id VARCHAR2(22) PATH '$')) j
                   WHERE j.review_id = p.review_id))""",
            model=model, revision=revision,
        )
        removed = cur.rowcount
        cur.execute("DELETE FROM cur_review_passage WHERE model_name <> :model", model=model)
        removed += cur.rowcount
        cur.execute(
            """SELECT r.business_id, r.review_id, r.review_text
               FROM cur_restaurant_doc d,
                    JSON_TABLE(d.review_ids, '$[*]' COLUMNS (review_id VARCHAR2(22) PATH '$')) j,
                    stg_review r
               WHERE r.review_id = j.review_id
                 AND NOT EXISTS (SELECT 1 FROM cur_review_passage p WHERE p.review_id = r.review_id AND p.model_name = :model)""",
            model=model,
        )
        pending = [
            (business_id, review_id, no, text)
            for business_id, review_id, review_text in cur
            for no, text in enumerate(split_passages(review_text), start=1)
        ]
    conn.commit()
    print(f"  model {model}@{revision[:10]}: {len(pending):,} passages to embed, {removed:,} stale removed")
    if not pending:
        return

    t0 = time.time()
    with conn.cursor() as cur:
        for i in range(0, len(pending), BATCH_SIZE):
            batch = pending[i:i + BATCH_SIZE]
            vectors = embeddings.embed_passages([text for *_, text in batch], model)
            cur.executemany(
                """INSERT INTO cur_review_passage
                     (business_id, review_id, passage_no, passage_text, model_name, model_revision, embedding)
                   VALUES (:1, :2, :3, :4, :5, :6, :7)""",
                [(b, r, n, t, model, revision, array.array("f", v)) for (b, r, n, t), v in zip(batch, vectors)],
            )
            conn.commit()
            done = min(i + BATCH_SIZE, len(pending))
            if done % 5120 < BATCH_SIZE or done == len(pending):
                print(f"  embedded {done:,}/{len(pending):,}")
    print(f"  {len(pending) / (time.time() - t0):.0f} passages/s")
