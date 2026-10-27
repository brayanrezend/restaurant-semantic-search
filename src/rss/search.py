import array
import re
import textwrap
import time
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

import oracledb

from rss import config, embeddings

TZ = ZoneInfo("America/Chicago")

FEATURES = {
    "outdoor_seating", "takes_reservations", "good_for_kids", "good_for_groups", "delivery", "takeout",
    "happy_hour", "dogs_allowed", "wheelchair_accessible", "byob", "has_tv", "table_service",
}

OPEN_STATUS = """
  CASE
    WHEN r.hours_status = 'MISSING' THEN 'UNKNOWN'
    WHEN EXISTS (
      SELECT 1 FROM cur_restaurant_hours h
      WHERE h.business_id = r.business_id
        AND (   (h.day_of_week = :dow AND h.slot_status = 'NORMAL' AND :minute >= h.open_min AND :minute < h.close_min)
             OR (h.day_of_week = :dow AND h.slot_status = 'OVERNIGHT' AND :minute >= h.open_min)
             OR (h.day_of_week = :prev_dow AND h.slot_status = 'OVERNIGHT' AND :minute < h.close_min))
    ) THEN 'OPEN'
    WHEN EXISTS (
      SELECT 1 FROM cur_restaurant_hours h
      WHERE h.business_id = r.business_id
        AND h.day_of_week IN (:dow, :prev_dow)
        AND h.slot_status IN ('AMBIGUOUS', 'INVALID')
    ) THEN 'UNKNOWN'
    ELSE 'CLOSED'
  END"""

TAGS = """
  (SELECT LISTAGG(t.tag, ',') WITHIN GROUP (ORDER BY t.tag_group, t.tag)
   FROM cur_restaurant_tag t
   WHERE t.business_id = r.business_id AND t.tag_group IN ('ambience', 'meal', 'music'))"""

POINT = "SDO_GEOMETRY(2001, 4326, SDO_POINT_TYPE(:lon, :lat, NULL), NULL, NULL)"
PASSAGE_CANDIDATES = 500
RRF_K = 60

NEIGHBORHOODS = {
    "French Quarter": (29.9574, -90.0631),
    "Marigny / Frenchmen St": (29.9640, -90.0577),
    "CBD": (29.9500, -90.0700),
    "Garden District": (29.9285, -90.0840),
    "Uptown / Magazine St": (29.9230, -90.1050),
    "Mid-City": (29.9750, -90.0950),
    "Bywater": (29.9630, -90.0420),
}

STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "but", "not", "are", "was", "you", "your", "can", "has", "have",
    "place", "spot", "somewhere", "restaurant", "good", "great", "best", "nice", "want", "looking", "some", "any",
    "where", "what", "from", "near", "really", "very", "bit", "more", "less", "eat", "eating", "willing",
    "spend", "spending", "money", "little", "lot", "much", "like", "would", "need", "get", "find", "had",
}


@dataclass
class SearchRequest:
    text: str = ""
    price_max: int | None = None
    min_stars: float | None = None
    category: str | None = None
    tags: list[str] = field(default_factory=list)
    features: list[str] = field(default_factory=list)
    free_wifi: bool = False
    open_now: bool = False
    at: datetime | None = None
    lat: float | None = None
    lon: float | None = None
    radius_km: float = 2.0
    k: int = 10
    model: str | None = None


def _clock(at: datetime | None) -> tuple[datetime, dict]:
    at = (at.replace(tzinfo=TZ) if at and at.tzinfo is None else at) or datetime.now(TZ)
    at = at.astimezone(TZ)
    dow = at.isoweekday()
    return at, {"dow": dow, "prev_dow": 7 if dow == 1 else dow - 1, "minute": at.hour * 60 + at.minute}


def build_sql(req: SearchRequest) -> tuple[str, dict]:
    unknown = set(req.features) - FEATURES
    if unknown:
        raise ValueError(f"unknown features: {sorted(unknown)}")

    binds: dict = {"model": req.model or config.EMBEDDING_MODEL, "k": req.k}
    where = []
    if req.price_max is not None:
        where.append("r.price_level <= :price_max")
        binds["price_max"] = req.price_max
    if req.min_stars is not None:
        where.append("r.stars >= :min_stars")
        binds["min_stars"] = req.min_stars
    if req.category:
        where.append("EXISTS (SELECT 1 FROM cur_restaurant_category c\n"
                     "            WHERE c.business_id = r.business_id AND c.category = :category)")
        binds["category"] = req.category
    for i, tag in enumerate(req.tags):
        where.append(f"EXISTS (SELECT 1 FROM cur_restaurant_tag t WHERE t.business_id = r.business_id AND t.tag = :tag{i})")
        binds[f"tag{i}"] = tag
    where += [f"r.{f}" for f in sorted(req.features)]
    if req.free_wifi:
        where.append("r.wifi = 'free'")

    geo = "CAST(NULL AS NUMBER)"
    if req.lat is not None and req.lon is not None:
        where.append(f"SDO_WITHIN_DISTANCE(r.geom, {POINT}, :sdo_params) = 'TRUE'")
        geo = f"ROUND(SDO_GEOM.SDO_DISTANCE(r.geom, {POINT}, 0.05, 'unit=KM'), 2)"
        binds.update(lat=req.lat, lon=req.lon, sdo_params=f"distance={req.radius_km} unit=KM")

    where_sql = "WHERE " + "\n    AND ".join(where) if where else ""
    open_filter = "WHERE open_status = 'OPEN'" if req.open_now else ""
    columns = """r.business_id, r.name, r.address, r.stars, r.review_count, r.price_level, r.categories,
         r.latitude, r.longitude, r.wifi, r.noise_level,"""

    if not req.text.strip():
        sql = f"""SELECT *
FROM (
  SELECT {columns}
         CAST(NULL AS NUMBER) AS distance,
         {geo} AS distance_km,
         {_nest(OPEN_STATUS)} AS open_status,
         {_nest(TAGS)} AS tags
  FROM cur_restaurant r
  {where_sql}
)
{open_filter}
ORDER BY stars DESC, review_count DESC
FETCH FIRST :k ROWS ONLY"""
        binds.pop("model")
        return "\n".join(line for line in sql.splitlines() if line.strip()), binds

    sql = f"""WITH candidates AS (
  SELECT r.business_id, VECTOR_DISTANCE(e.embedding, :qv, COSINE) AS doc_distance
  FROM cur_restaurant r
  JOIN cur_restaurant_embedding e ON e.business_id = r.business_id AND e.model_name = :model
  {where_sql}
),
passage_hits AS (
  SELECT business_id, MIN(distance) AS passage_distance
  FROM (
    SELECT p.business_id, VECTOR_DISTANCE(p.embedding, :qv, COSINE) AS distance
    FROM cur_review_passage p
    ORDER BY VECTOR_DISTANCE(p.embedding, :qv, COSINE)
    FETCH APPROX FIRST {PASSAGE_CANDIDATES} ROWS ONLY WITH TARGET ACCURACY 90
  )
  GROUP BY business_id
),
ranked AS (
  SELECT c.business_id, c.doc_distance,
         1 / ({RRF_K} + RANK() OVER (ORDER BY c.doc_distance))
         + CASE WHEN h.passage_distance IS NULL THEN 0
                ELSE 1 / ({RRF_K} + RANK() OVER (ORDER BY h.passage_distance NULLS LAST)) END AS score
  FROM candidates c
  LEFT JOIN passage_hits h ON h.business_id = c.business_id
)
SELECT *
FROM (
  SELECT {columns}
         k.doc_distance AS distance,
         k.score,
         {geo} AS distance_km,
         {_nest(OPEN_STATUS)} AS open_status,
         {_nest(TAGS)} AS tags
  FROM ranked k
  JOIN cur_restaurant r ON r.business_id = k.business_id
)
{open_filter}
ORDER BY score DESC
FETCH FIRST :k ROWS ONLY"""
    return "\n".join(line for line in sql.splitlines() if line.strip()), binds


def search(conn: oracledb.Connection, req: SearchRequest) -> dict:
    sql, binds = build_sql(req)
    at, clock = _clock(req.at)
    binds.update(clock)

    t0 = time.perf_counter()
    if req.text.strip():
        binds["qv"] = array.array("f", embeddings.embed_query(req.text, req.model))
    t1 = time.perf_counter()
    with conn.cursor() as cur:
        cur.execute(sql, binds)
        cols = [d[0].lower() for d in cur.description]
        rows = [dict(zip(cols, row)) for row in cur]
    t2 = time.perf_counter()

    for row in rows:
        row["tags"] = row["tags"].split(",") if row["tags"] else []
    evidence_sql = None
    if "qv" in binds and rows and binds["model"] == config.EMBEDDING_MODEL:
        evidence_sql, quotes = evidence(conn, [r["business_id"] for r in rows], binds["qv"])
        for row in rows:
            row["evidence"] = (quotes.get(row["business_id"]) or [None])[0]
    t3 = time.perf_counter()

    params = {k: v for k, v in binds.items() if k != "qv"}
    if "qv" in binds:
        params["qv"] = f"VECTOR(384) of '{req.text.strip()}'"
    return {
        "results": rows,
        "at": at.isoformat(timespec="minutes"),
        "day_of_week": clock["dow"],
        "terms": sorted(_terms(req.text)),
        "timing_ms": {
            "embed": round((t1 - t0) * 1000, 1),
            "sql": round((t2 - t1) * 1000, 1),
            "evidence": round((t3 - t2) * 1000, 1),
        },
        "sql": sql,
        "evidence_sql": evidence_sql,
        "params": params,
    }


def _terms(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z']+", text.lower()) if len(w) > 2 and w not in STOPWORDS}


def evidence(
    conn: oracledb.Connection, ids: list[str], qv: array.array, per_business: int = 1
) -> tuple[str, dict[str, list[dict]]]:
    names = ", ".join(f":id{i}" for i in range(len(ids)))
    sql = f"""SELECT business_id, review_id, passage_text, distance
FROM (
  SELECT p.business_id, p.review_id, p.passage_text,
         VECTOR_DISTANCE(p.embedding, :qv, COSINE) AS distance,
         ROW_NUMBER() OVER (PARTITION BY p.business_id ORDER BY VECTOR_DISTANCE(p.embedding, :qv, COSINE)) AS rn
  FROM cur_review_passage p
  WHERE p.model_name = :model
    AND p.business_id IN ({names})
)
WHERE rn <= {per_business}
ORDER BY business_id, rn"""
    binds = {"qv": qv, "model": config.EMBEDDING_MODEL, **{f"id{i}": v for i, v in enumerate(ids)}}
    quotes: dict[str, list[dict]] = {}
    with conn.cursor() as cur:
        cur.execute(sql, binds)
        for b, r, t, d in cur:
            quotes.setdefault(b, []).append({"review_id": r, "text": t, "distance": d})
    return sql, quotes


def get_restaurant(conn: oracledb.Connection, business_id: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT business_id, name, address, postal_code, stars, review_count, price_level, categories,
                      latitude, longitude, wifi, alcohol, noise_level, attire, hours_status
               FROM cur_restaurant WHERE business_id = :1""",
            [business_id],
        )
        row = cur.fetchone()
        if not row:
            return None
        restaurant = dict(zip([d[0].lower() for d in cur.description], row))

        cur.execute(
            """SELECT day_of_week, open_min, close_min, slot_status FROM cur_restaurant_hours
               WHERE business_id = :1 ORDER BY day_of_week""",
            [business_id],
        )
        restaurant["hours"] = [
            {"day": d, "open": _hhmm(o), "close": _hhmm(c), "status": s} for d, o, c, s in cur
        ]

        cur.execute("SELECT tag_group, tag FROM cur_restaurant_tag WHERE business_id = :1 ORDER BY 1, 2", [business_id])
        restaurant["tags"] = [f"{g}:{t}" for g, t in cur]

        cur.execute(
            """SELECT stars, review_date, DBMS_LOB.SUBSTR(review_text, 600, 1)
               FROM stg_review r
               WHERE business_id = :1
                 AND NOT EXISTS (SELECT 1 FROM v_dq_quarantine q WHERE q.table_name = 'stg_review' AND q.record_key = r.review_id)
               ORDER BY useful DESC, review_date DESC
               FETCH FIRST 3 ROWS ONLY""",
            [business_id],
        )
        restaurant["reviews"] = [{"stars": s, "date": d.date().isoformat(), "text": t} for s, d, t in cur]
    return restaurant


def facets(conn: oracledb.Connection) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT category, COUNT(*) FROM cur_restaurant_category
               WHERE category NOT IN ('Restaurants', 'Food')
               GROUP BY category HAVING COUNT(*) >= 10 ORDER BY 2 DESC"""
        )
        categories = [{"name": c, "count": n} for c, n in cur]
        cur.execute("SELECT tag_group, tag, COUNT(*) FROM cur_restaurant_tag GROUP BY tag_group, tag ORDER BY 1, 3 DESC")
        tags: dict[str, list] = {}
        for group, tag, n in cur:
            tags.setdefault(group, []).append({"name": tag, "count": n})
    neighborhoods = [{"name": n, "lat": lat, "lon": lon} for n, (lat, lon) in NEIGHBORHOODS.items()]
    return {"categories": categories, "tags": tags, "features": sorted(FEATURES), "neighborhoods": neighborhoods}


def _nest(fragment: str) -> str:
    return textwrap.indent(textwrap.dedent(fragment).strip(), " " * 9).lstrip()


def _hhmm(minutes: int | None) -> str | None:
    return None if minutes is None else f"{minutes // 60:02d}:{minutes % 60:02d}"
