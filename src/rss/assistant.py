import array
import hashlib
import json
import re
import unicodedata

import oracledb

from rss import config, embeddings, llm, search

PROMPT_VERSION = "v11"

TAG_CHOICES = ["romantic", "intimate", "classy", "trendy", "casual", "divey", "hipster", "upscale", "touristy",
               "brunch", "latenight", "dessert", "live"]
PT_WORDS = {"de", "que", "para", "com", "uma", "um", "nao", "quero", "lugar", "comer", "barato", "barata", "perto",
            "no", "na", "do", "da", "em", "mas", "bem", "muito", "pouco", "jantar", "almoco", "onde", "aberto"}
EN_WORDS = {"the", "and", "for", "with", "an", "to", "want", "place", "near", "cheap", "good", "of", "in", "but",
            "very", "some", "spot", "dinner", "lunch", "where", "open", "best"}
PRICE_WORDS = {1: "inexpensive", 2: "moderate", 3: "pricey", 4: "very expensive"}
FEATURE_CHOICES = ["outdoor_seating", "takes_reservations", "good_for_kids", "good_for_groups", "dogs_allowed",
                   "happy_hour", "byob"]

PARSE_SYSTEM = """You turn a restaurant search request into search parameters for a New Orleans restaurant search engine.
The request may be in any language; always write semantic_query in English.

- semantic_query: what the person wants to eat, drink or experience, in a few English words, without price, rating, location or opening-hours words.
- Set a filter only when the request explicitly asks for it. Most requests set zero to two filters; everything else stays null, false or empty.
- A dish (gumbo, po'boy, pasta, oysters) is not a category; keep it in semantic_query.
- "best" or "good" alone is not a rating; min_stars needs words about ratings or reviews.
- price_max is a ceiling: use it only when the person wants to spend little or stay below a price. If they are willing to spend more, leave it null.
- open_now only for words like now, tonight or open; free_wifi only for WiFi, laptop or working.
- For a street or area, use the neighborhood that contains it."""

PARSE_EXAMPLES = [
    ("affordable tacos where I can work on my laptop",
     {"semantic_query": "tacos", "price_max": 1, "min_stars": None, "category": "Tacos", "free_wifi": True,
      "open_now": False, "near": None, "tags": [], "features": []}),
    ("best jambalaya in town",
     {"semantic_query": "jambalaya", "price_max": None, "min_stars": None, "category": None, "free_wifi": False,
      "open_now": False, "near": None, "tags": [], "features": []}),
    ("jantar romântico no Garden District aberto agora",
     {"semantic_query": "romantic dinner", "price_max": None, "min_stars": None, "category": None, "free_wifi": False,
      "open_now": True, "near": "Garden District", "tags": ["romantic"], "features": []}),
    ("highly rated Thai food on Frenchmen Street",
     {"semantic_query": "Thai food", "price_max": None, "min_stars": 4.5, "category": "Thai", "free_wifi": False,
      "open_now": False, "near": "Marigny / Frenchmen St", "tags": [], "features": []}),
    ("a quiet spot for coffee and pastries",
     {"semantic_query": "quiet spot for coffee and pastries", "price_max": None, "min_stars": None, "category": None,
      "free_wifi": False, "open_now": False, "near": None, "tags": [], "features": []}),
    ("family dinner with the kids, outdoor seating please",
     {"semantic_query": "family dinner", "price_max": None, "min_stars": None, "category": None, "free_wifi": False,
      "open_now": False, "near": None, "tags": [], "features": ["good_for_kids", "outdoor_seating"]}),
]

GUARDS = {
    "price_max": ["cheap", "inexpensive", "affordable", "budget", "low cost", "under", "below", "less", "little",
                  "moderate", "not too expensive", "reasonabl", "barat", "econom", "pouco", "menos", "em conta"],
    "open_now": ["now", "tonight", "open", "agora", "hoje", "aberto", "aberta"],
    "free_wifi": ["wifi", "wi-fi", "laptop", "notebook", "work", "trabalh", "internet"],
    "min_stars": ["rated", "rating", "review", "star", "avalia", "estrela", "nota"],
    "outdoor_seating": ["outdoor", "outside", "patio", "terrace", "ar livre", "area externa", "varanda"],
    "takes_reservations": ["reserv"],
    "good_for_kids": ["kid", "child", "family", "crianc", "filho", "familia"],
    "good_for_groups": ["group", "friends", "party", "grupo", "amigos", "galera"],
    "dogs_allowed": ["dog", "pet", "cachorro", "cao"],
    "happy_hour": ["happy hour"],
    "byob": ["byob", "bring your own", "levar"],
    "romantic": ["romant", "date", "encontro", "namor", "anniversary", "aniversario"],
    "intimate": ["intimate", "cozy", "intimo", "aconcheg"],
    "classy": ["classy", "elegant", "fancy", "chique", "elegante"],
    "trendy": ["trendy", "hip", "modern", "badalad", "moderno"],
    "casual": ["casual", "relaxed", "descontraid"],
    "divey": ["dive", "divey", "boteco", "buteco"],
    "hipster": ["hipster"],
    "upscale": ["upscale", "fancy", "luxur", "fine dining", "sofisticad", "fino", "chique"],
    "touristy": ["touristy", "tourist", "turist"],
    "brunch": ["brunch"],
    "latenight": ["late", "midnight", "madrugada", "tarde da noite"],
    "dessert": ["dessert", "sweet", "sobremesa", "doce"],
    "live": ["live", "music", "jazz", "band", "musica", "ao vivo", "show"],
}

EXPLAIN_SYSTEM = """You explain why restaurants match a search request, using only the facts and review quotes provided.
For each numbered restaurant, write one sentence of at most 30 words saying what in the facts or quotes matches the request.
Write in the language of the request. The facts are correct: never contradict them, and do not invent dishes, prices, hours or details.
When the request mentions a time of day (breakfast, lunch, dinner, late night), check the hours.
If a restaurant only partly matches, say what matches and what does not."""

EXPLAIN_EXAMPLES = [
    (
        'Request: "lugar barato para tomar café da manhã"\n\n'
        "Restaurant 1: Sunrise Beignet Stand\nFacts: 4.0 stars; price: $ (inexpensive); hours: daily 06:00-14:00; Breakfast & Brunch, Cafes; good for: casual, breakfast\n"
        'Review quotes:\n- "Beignets and coffee for a few dollars."\n\n'
        "Write one reason per restaurant, in Portuguese.",
        json.dumps({"1": "Café da manhã barato ($) com beignets e café por poucos dólares, segundo as avaliações."},
                   ensure_ascii=False),
    ),
    (
        'Request: "quiet place for a business lunch"\n\n'
        "Restaurant 1: Café Lune\nFacts: 4.5 stars; price: $$ (moderate); hours: daily 11:00-15:00; French, Cafes; good for: classy, lunch; wifi: free; noise: quiet\n"
        'Review quotes:\n- "Calm room, perfect for talking business over a long lunch."\n\n'
        "Restaurant 2: Big Easy Wings\nFacts: 4.0 stars; price: $ (inexpensive); hours: daily 18:00-02:00; Chicken Wings, Sports Bars; good for: casual; noise: loud\n"
        'Review quotes:\n- "TVs everywhere and the game is always on."\n\n'
        "Write one reason per restaurant, in English.",
        json.dumps({
            "1": "Quiet, classy French café that reviewers call perfect for business talk over lunch.",
            "2": "Inexpensive, but it only opens at 18:00 and is loud with games on TV, a poor fit for a business lunch.",
        }),
    )
]


def _nullable(schema: dict) -> dict:
    return {"anyOf": [schema, {"type": "null"}]}


def _parse_schema(categories: list[str]) -> dict:
    limit = {"maxItems": 3} if config.LLM_PROVIDER == "ollama" else {}
    properties = {
        "semantic_query": {"type": "string"},
        "price_max": _nullable({"type": "integer", "enum": [1, 2, 3]}),
        "min_stars": _nullable({"type": "number", "enum": [4, 4.5]}),
        "category": _nullable({"type": "string", "enum": categories}),
        "free_wifi": {"type": "boolean"},
        "open_now": {"type": "boolean"},
        "near": _nullable({"type": "string", "enum": list(search.NEIGHBORHOODS)}),
        "tags": {"type": "array", "items": {"type": "string", "enum": TAG_CHOICES}, **limit},
        "features": {"type": "array", "items": {"type": "string", "enum": FEATURE_CHOICES}, **limit},
    }
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def _category_grounded(category: str, text: str) -> bool:
    text = _normalize(text)
    for word in re.findall(r"[a-z]+", _normalize(category)):
        stem = word.rstrip("s")
        if len(stem) >= 5 and stem[:5] in text:
            return True
        if 3 <= len(stem) <= 4 and re.search(rf"\b{stem}s?\b", text):
            return True
    return False


def _validate_parse(raw: dict, question: str, categories: list[str]) -> tuple[dict, int]:
    dropped = 0
    text = _normalize(question)

    def grounded(key: str) -> bool:
        nonlocal dropped
        if any(re.search(r"\b" + re.escape(word), text) for word in GUARDS[key]):
            return True
        dropped += 1
        return False

    def pick(value, allowed):
        nonlocal dropped
        if value is None:
            return None
        if value in allowed:
            return value
        dropped += 1
        return None

    def pick_list(values, allowed):
        nonlocal dropped
        values = values if isinstance(values, list) else []
        kept = [v for v in dict.fromkeys(values) if v in allowed]
        dropped += len(values) - len(kept)
        return kept

    min_stars = pick(raw.get("min_stars"), {4, 4.5})
    price_max = pick(raw.get("price_max"), {1, 2, 3})
    semantic = str(raw.get("semantic_query") or "").strip()[:200]
    category = pick(raw.get("category"), set(categories))
    if category is not None and not _category_grounded(category, text + " " + semantic):
        category = None
        dropped += 1
    filters = {
        "price_max": price_max if price_max is None or grounded("price_max") else None,
        "min_stars": min_stars if min_stars is None or grounded("min_stars") else None,
        "category": category,
        "tags": [t for t in pick_list(raw.get("tags"), set(TAG_CHOICES)) if grounded(t)],
        "features": [f for f in pick_list(raw.get("features"), set(FEATURE_CHOICES)) if grounded(f)],
        "free_wifi": raw.get("free_wifi") is True and grounded("free_wifi"),
        "open_now": raw.get("open_now") is True and grounded("open_now"),
        "near": pick(raw.get("near"), set(search.NEIGHBORHOODS)),
    }
    return {"semantic_query": semantic, "filters": filters}, dropped


def parse_question(conn: oracledb.Connection, question: str) -> dict:
    facets = search.facets(conn)
    categories = [c["name"] for c in facets["categories"]]
    schema = _parse_schema(categories)
    examples = [(q, json.dumps(a)) for q, a in PARSE_EXAMPLES]
    key = _cache_key("parse", question, json.dumps(schema, sort_keys=True))

    cached = _cache_get(conn, key)
    result = None
    try:
        if cached is None:
            result = llm.complete_json(PARSE_SYSTEM, question, schema, examples=examples)
        raw = cached if cached is not None else result.output
        parsed, dropped = _validate_parse(raw, question, categories)
    except llm.LLMError as e:
        _log(conn, "parse", question, None, False, error=str(e))
        raise
    _log(conn, "parse", question, result, True, cache_hit=cached is not None, dropped=dropped, output=raw)
    if cached is None:
        _cache_put(conn, key, "parse", raw)
    translated = _language(question) == "Portuguese" and parsed["semantic_query"]
    search_text = parsed["semantic_query"] if translated else question
    return {**parsed, "search_text": search_text, "llm": _meta(result, cached is not None, dropped, raw)}


def explain_results(conn: oracledb.Connection, question: str, query: str, business_ids: list[str]) -> dict:
    ids = list(dict.fromkeys(business_ids))[:5]
    facts = _facts(conn, ids)
    ids = [i for i in ids if i in facts]
    if not ids:
        return {"items": [], "llm": None}

    qv = array.array("f", embeddings.embed_query(query or question))
    _, quotes = search.evidence(conn, ids, qv, per_business=3)
    blocks = [
        f"Restaurant {n}: {facts[i]['name']}\nFacts: {facts[i]['facts']}\nReview quotes:\n"
        + "\n".join(f'- "{q["text"]}"' for q in quotes.get(i, []))
        for n, i in enumerate(ids, start=1)
    ]
    user = (f'Request: "{question}"\n\n' + "\n\n".join(blocks)
            + f"\n\nWrite one reason per restaurant, in {_language(question)}.")
    keys = [str(n) for n in range(1, len(ids) + 1)]
    schema = {
        "type": "object",
        "properties": {k: {"type": "string"} for k in keys},
        "required": keys,
        "additionalProperties": False,
    }
    key = _cache_key("explain", question, user)

    cached = _cache_get(conn, key)
    result = None
    try:
        if cached is None:
            result = llm.complete_json(EXPLAIN_SYSTEM, user, schema, max_tokens=1024, examples=EXPLAIN_EXAMPLES)
        raw = cached if cached is not None else result.output
    except llm.LLMError as e:
        _log(conn, "explain", question, None, False, error=str(e))
        raise
    items = [
        {"business_id": i, "reason": str(raw.get(k, "")).strip()[:300]}
        for k, i in zip(keys, ids)
        if str(raw.get(k, "")).strip()
    ]
    dropped = len(ids) - len(items)
    _log(conn, "explain", question, result, True, cache_hit=cached is not None, dropped=dropped, output=raw)
    if cached is None:
        _cache_put(conn, key, "explain", raw)
    return {"items": items, "llm": _meta(result, cached is not None, dropped, raw)}


def _facts(conn: oracledb.Connection, ids: list[str]) -> dict[str, dict]:
    if not ids:
        return {}
    names = ", ".join(f":id{i}" for i in range(len(ids)))
    binds = {f"id{i}": v for i, v in enumerate(ids)}
    with conn.cursor() as cur:
        cur.execute(
            f"""SELECT r.business_id, r.name, r.address, r.stars, r.price_level, r.categories, r.wifi, r.alcohol,
                       r.noise_level, (SELECT LISTAGG(t.tag, ', ') WITHIN GROUP (ORDER BY t.tag_group, t.tag)
                        FROM cur_restaurant_tag t
                        WHERE t.business_id = r.business_id AND t.tag_group IN ('ambience', 'meal', 'music')) AS tags
                FROM cur_restaurant r WHERE r.business_id IN ({names})""",
            binds,
        )
        cols = [d[0].lower() for d in cur.description]
        rows = [dict(zip(cols, row)) for row in cur]
        cur.execute(
            f"""SELECT business_id, day_of_week, open_min, close_min FROM cur_restaurant_hours
                WHERE business_id IN ({names}) ORDER BY business_id, day_of_week""",
            binds,
        )
        hours: dict[str, dict[int, str]] = {}
        for business_id, day, open_min, close_min in cur:
            slot = f"{open_min // 60:02d}:{open_min % 60:02d}-{close_min // 60:02d}:{close_min % 60:02d}" if open_min is not None else "unclear"
            hours.setdefault(business_id, {})[day] = slot
    facts = {}
    for r in rows:
        parts = [
            r["address"] and f"address: {r['address']}",
            f"{r['stars']} stars",
            r["price_level"] and f"price: {'$' * r['price_level']} ({PRICE_WORDS[r['price_level']]})",
            f"hours: {_hours_text(hours.get(r['business_id']))}",
            r["categories"],
            r["tags"] and f"good for: {r['tags']}",
            r["wifi"] and f"wifi: {r['wifi']}",
            r["alcohol"] and f"alcohol: {r['alcohol'].replace('_', ' ')}",
            r["noise_level"] and f"noise: {r['noise_level'].replace('_', ' ')}",
        ]
        facts[r["business_id"]] = {"name": r["name"], "facts": "; ".join(p for p in parts if p)}
    return facts


def _language(question: str) -> str:
    words = re.findall(r"[a-z']+", _normalize(question))
    pt = sum(w in PT_WORDS for w in words) + 2 * bool(re.search(r"[ãõçáéíóúâêô]", question.lower()))
    en = sum(w in EN_WORDS for w in words)
    if pt > en:
        return "Portuguese"
    if en > pt:
        return "English"
    return "the same language as the request"


def _hours_text(days: dict[int, str] | None) -> str:
    if not days:
        return "unknown"
    if len(days) == 7 and len(set(days.values())) == 1:
        return f"daily {days[1]}"
    names = ["", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    return ", ".join(f"{names[d]} {days[d]}" if d in days else f"{names[d]} closed" for d in range(1, 8))


def _cache_key(role: str, question: str, extra: str) -> str:
    raw = "\x1f".join([PROMPT_VERSION, role, config.LLM_PROVIDER, config.LLM_MODEL, question.strip().lower(), extra])
    return hashlib.sha256(raw.encode()).hexdigest()


def _cache_get(conn: oracledb.Connection, key: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute("SELECT output FROM llm_cache WHERE cache_key = :1", [key])
        row = cur.fetchone()
    if not row:
        return None
    return json.loads(json.dumps(row[0], default=lambda d: int(d) if d == int(d) else float(d)))


def _cache_put(conn: oracledb.Connection, key: str, role: str, output: dict) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """MERGE INTO llm_cache t USING (SELECT :cache_key AS cache_key FROM dual) s ON (t.cache_key = s.cache_key)
               WHEN NOT MATCHED THEN INSERT (cache_key, role, model, output)
                    VALUES (:cache_key, :role, :model, JSON(:output))""",
            cache_key=key, role=role, model=config.LLM_MODEL, output=json.dumps(output),
        )
    conn.commit()


def _log(conn, role, question, result, success, cache_hit=False, dropped=None, error=None, output=None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO llm_call (role, provider, model, question, cache_hit, success, latency_ms, input_tokens,
                                     output_tokens, dropped_items, error_message, output)
               VALUES (:1, :2, :3, :4, :5, :6, :7, :8, :9, :10, :11, JSON(:12))""",
            [role, config.LLM_PROVIDER, config.LLM_MODEL, question[:1000], cache_hit, success,
             round(result.latency_ms) if result else None,
             result.input_tokens if result else None, result.output_tokens if result else None,
             dropped, error[:1000] if error else None, json.dumps(output) if output is not None else None],
        )
    conn.commit()


def _meta(result: llm.LLMResult | None, cache_hit: bool, dropped: int, raw: dict) -> dict:
    return {
        "provider": config.LLM_PROVIDER,
        "model": result.model if result else config.LLM_MODEL,
        "cache_hit": cache_hit,
        "latency_ms": round(result.latency_ms) if result else 0,
        "input_tokens": result.input_tokens if result else None,
        "output_tokens": result.output_tokens if result else None,
        "dropped_items": dropped,
        "raw": raw,
    }
