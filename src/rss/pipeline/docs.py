import hashlib
import json
from collections import defaultdict

import oracledb

DOC_BUDGET = 2000
REVIEW_CHARS = 400
REVIEWS_PER_DOC = 8

PRICE = {1: "inexpensive", 2: "moderately priced", 3: "pricey", 4: "very expensive"}
WIFI = {"free": "free WiFi", "paid": "paid WiFi", "no": "no WiFi"}
ALCOHOL = {"full_bar": "full bar", "beer_and_wine": "beer and wine only", "none": "no alcohol"}
FLAGS = {
    "takes_reservations": "takes reservations",
    "outdoor_seating": "outdoor seating",
    "good_for_kids": "good for kids",
    "good_for_groups": "good for groups",
    "delivery": "delivery",
    "takeout": "takeout",
    "has_tv": "has TVs",
    "happy_hour": "happy hour",
    "dogs_allowed": "dog friendly",
    "wheelchair_accessible": "wheelchair accessible",
    "byob": "BYOB",
}
TAG_LABELS = {"ambience": "Ambience", "meal": "Good for", "music": "Music", "parking": "Parking"}
GENERIC_CATEGORIES = {"Restaurants", "Food"}


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "..."


def build_doc(
    r: dict, categories: list[str], tags: dict[str, list[str]], reviews: list[tuple[str, str]]
) -> tuple[str, list[str]]:
    cats = [c for c in categories if c not in GENERIC_CATEGORIES]
    lines = [f"{r['name']}. {', '.join(cats) or 'Restaurant'} in New Orleans."]

    facts = []
    if r["price_level"] in PRICE:
        facts.append(PRICE[r["price_level"]])
    if r["noise_level"]:
        facts.append(f"{r['noise_level'].replace('_', ' ')} noise level")
    if r["attire"]:
        facts.append(f"{r['attire']} attire")
    if r["wifi"] in WIFI:
        facts.append(WIFI[r["wifi"]])
    if r["alcohol"] in ALCOHOL:
        facts.append(ALCOHOL[r["alcohol"]])
    facts += [label for col, label in FLAGS.items() if r[col]]
    if facts:
        text = ", ".join(facts)
        lines.append(f"{text[0].upper()}{text[1:]}.")

    for group, label in TAG_LABELS.items():
        if tags.get(group):
            lines.append(f"{label}: {', '.join(t.replace('_', ' ') for t in tags[group])}.")

    doc = " ".join(lines) + "\nReviews:"
    used = []
    for review_id, text in reviews:
        snippet = f"\n- {_clip(text, REVIEW_CHARS)}"
        if len(doc) + len(snippet) > DOC_BUDGET:
            break
        doc += snippet
        used.append(review_id)
    return doc, used


def _fetch(conn: oracledb.Connection):
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT business_id, name, price_level, noise_level, attire, wifi, alcohol, {", ".join(FLAGS)}
            FROM cur_restaurant""")
        cols = [d[0].lower() for d in cur.description]
        restaurants = [dict(zip(cols, row)) for row in cur]

        cur.execute("SELECT business_id, category FROM cur_restaurant_category ORDER BY business_id, category")
        categories = defaultdict(list)
        for business_id, category in cur:
            categories[business_id].append(category)

        cur.execute("SELECT business_id, tag_group, tag FROM cur_restaurant_tag ORDER BY business_id, tag_group, tag")
        tags = defaultdict(lambda: defaultdict(list))
        for business_id, group, tag in cur:
            tags[business_id][group].append(tag)

        cur.execute(f"""
            SELECT business_id, review_id, review_text
            FROM (
              SELECT r.business_id, r.review_id, r.review_text,
                     ROW_NUMBER() OVER (PARTITION BY r.business_id ORDER BY r.useful DESC, r.review_date DESC, r.review_id) AS rn
              FROM stg_review r
              JOIN cur_restaurant c ON c.business_id = r.business_id
              WHERE NOT EXISTS (SELECT 1 FROM v_dq_quarantine q WHERE q.table_name = 'stg_review' AND q.record_key = r.review_id)
            )
            WHERE rn <= {REVIEWS_PER_DOC}
            ORDER BY business_id, rn""")
        reviews = defaultdict(list)
        for business_id, review_id, text in cur:
            reviews[business_id].append((review_id, text))
    return restaurants, categories, tags, reviews


def build_docs(conn: oracledb.Connection) -> None:
    restaurants, categories, tags, reviews = _fetch(conn)
    rows = []
    for r in restaurants:
        bid = r["business_id"]
        doc, used = build_doc(r, categories[bid], tags[bid], reviews[bid])
        rows.append((bid, doc, hashlib.sha256(doc.encode()).hexdigest(), json.dumps(used)))

    with conn.cursor() as cur:
        cur.setinputsizes(None, oracledb.DB_TYPE_CLOB, None, None)
        cur.executemany(
            """MERGE INTO cur_restaurant_doc t
               USING (SELECT :1 AS business_id, :2 AS doc_text, :3 AS doc_hash, :4 AS review_ids FROM dual) s
               ON (t.business_id = s.business_id)
               WHEN MATCHED THEN UPDATE SET t.doc_text = s.doc_text, t.doc_hash = s.doc_hash,
                    t.review_ids = JSON(s.review_ids), t.built_at = SYSTIMESTAMP
                    WHERE t.doc_hash <> s.doc_hash
               WHEN NOT MATCHED THEN INSERT (business_id, doc_text, doc_hash, review_ids)
                    VALUES (s.business_id, s.doc_text, s.doc_hash, JSON(s.review_ids))""",
            rows,
        )
        changed = cur.rowcount
    conn.commit()
    sizes = sorted(len(r[1]) for r in rows)
    print(f"  {len(rows):,} docs, {changed:,} new or changed; chars p50={sizes[len(sizes) // 2]} max={sizes[-1]}")
