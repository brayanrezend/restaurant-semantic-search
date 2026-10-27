import json
import os
import random
import string
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock

from rss import config, llm, search

DEMO_DIR = Path(os.getenv("DEMO_DIR", "/app/demo"))
SEED = 42
REVIEWS_PER_RESTAURANT = 22
WORKERS = 3
CACHE_FILE = DEMO_DIR / ".reviews-cache.jsonl"

LUNCH_DINNER = {d: "11:0-22:0" for d in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")}
BREAKFAST = {d: "7:0-15:0" for d in ("Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")}
CAFE = {d: "7:0-19:0" for d in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")}
NIGHT = {d: "18:0-2:0" for d in ("Wednesday", "Thursday", "Friday", "Saturday", "Sunday")}
LATE = {d: "20:0-4:0" for d in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")}
DINNER = {d: "17:30-22:0" for d in ("Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")}

STREETS = {
    "French Quarter": ["Decatur St", "Chartres St", "Royal St", "Dauphine St", "Toulouse St"],
    "Marigny / Frenchmen St": ["Frenchmen St", "Chartres St", "Royal St", "Elysian Fields Ave"],
    "CBD": ["Poydras St", "Magazine St", "Carondelet St", "Tchoupitoulas St"],
    "Garden District": ["Prytania St", "Magazine St", "Washington Ave", "Jackson Ave"],
    "Uptown / Magazine St": ["Magazine St", "Freret St", "Oak St", "Maple St"],
    "Mid-City": ["Carrollton Ave", "Canal St", "Bienville St", "Orleans Ave"],
    "Bywater": ["St Claude Ave", "Burgundy St", "Dauphine St", "Piety St"],
}

PROFILES = [
    {"cuisine": "Cajun and Creole cooking", "categories": "Cajun/Creole, Southern, Restaurants", "price": 2,
     "dishes": "gumbo, jambalaya, shrimp and grits, crawfish étouffée", "ambience": ["casual"], "meals": ["lunch", "dinner"],
     "hours": LUNCH_DINNER, "alcohol": "full_bar", "noise": "average", "wifi": "no",
     "names": ["Roux & Rye Kitchen", "Bayou Lantern", "Tante Odile's Table", "Gris-Gris Gumbo House", "Pelican Creole Kitchen"]},
    {"cuisine": "oyster bar and seafood", "categories": "Seafood, Bars, Restaurants", "price": 2,
     "dishes": "raw and chargrilled oysters, boiled crawfish, fried catfish, cold beer", "ambience": ["casual"],
     "meals": ["lunch", "dinner"], "hours": LUNCH_DINNER, "alcohol": "full_bar", "noise": "loud", "wifi": "no",
     "names": ["Half Shell Harbor", "Saltmarsh Oyster Bar", "Pirogue Seafood House", "Tidewater Raw Bar", "Shrimp Boat Social"]},
    {"cuisine": "po-boy sandwich shop", "categories": "Sandwiches, Delis, Restaurants", "price": 1,
     "dishes": "roast beef debris po-boy, fried shrimp po-boy, muffuletta", "ambience": ["casual", "divey"],
     "meals": ["lunch"], "hours": CAFE, "alcohol": "beer_and_wine", "noise": "average", "wifi": "no",
     "names": ["Levee Po-Boys", "Streetcar Sandwich Shop", "Debris & Gravy", "Corner Store Po-Boys", "Neutral Ground Deli"]},
    {"cuisine": "pizzeria", "categories": "Pizza, Italian, Restaurants", "price": 1,
     "dishes": "wood-fired pizza, garlic knots, pizza by the slice", "ambience": ["casual"], "meals": ["lunch", "dinner"],
     "hours": LUNCH_DINNER, "alcohol": "beer_and_wine", "noise": "average", "wifi": "free",
     "names": ["Second Line Pizza", "Crescent Slice", "Brick Oven Bywater", "Dough Rouge Pizzeria", "Magnolia Pie Co."]},
    {"cuisine": "cozy Italian trattoria", "categories": "Italian, Wine Bars, Restaurants", "price": 3,
     "dishes": "handmade pasta, cacio e pepe, tiramisu, Italian wine", "ambience": ["romantic", "intimate", "classy"],
     "meals": ["dinner"], "hours": DINNER, "alcohol": "full_bar", "noise": "quiet", "wifi": "no", "reservations": True,
     "names": ["Nonna Rosaria", "Via Esplanade Trattoria", "Fig & Fennel", "Little Palermo", "Casa Vincenzo"]},
    {"cuisine": "coffee shop where people work on laptops", "categories": "Coffee & Tea, Cafes, Restaurants", "price": 1,
     "dishes": "chicory latte, cold brew, breakfast sandwiches, pastries", "ambience": ["hipster", "casual"],
     "meals": ["breakfast"], "hours": CAFE, "alcohol": "none", "noise": "quiet", "wifi": "free",
     "names": ["Chicory Commons", "Steam & Shutter Café", "Paper Crane Coffee", "Satsuma Study Café", "Gallery Grind"]},
    {"cuisine": "brunch spot with bottomless mimosas", "categories": "Breakfast & Brunch, American (New), Restaurants",
     "price": 2, "dishes": "chicken and waffles, bananas foster french toast, bottomless mimosas", "ambience": ["trendy"],
     "meals": ["brunch", "breakfast"], "hours": BREAKFAST, "alcohol": "full_bar", "noise": "loud", "wifi": "free",
     "names": ["Sunday Parade Brunch", "Bottomless Bloom", "Porch & Biscuit", "Morning Second Line", "Golden Hour Brunch Club"]},
    {"cuisine": "jazz club with live music and cocktails", "categories": "Jazz & Blues, Bars, Nightlife, Restaurants",
     "price": 2, "dishes": "live jazz every night, sazeracs, small plates", "ambience": ["classy", "intimate"],
     "meals": ["latenight", "dinner"], "music": ["live"], "hours": NIGHT, "alcohol": "full_bar", "noise": "loud",
     "wifi": "no", "near": ["Marigny / Frenchmen St", "French Quarter"],
     "names": ["Blue Trombone Room", "Night Owl on Frenchmen", "Velvet Snare Jazz Bar", "Muskrat Ramble Lounge", "Late Set Supper Club"]},
    {"cuisine": "rooftop cocktail bar with a view", "categories": "Cocktail Bars, Lounges, Nightlife, Restaurants",
     "price": 3, "dishes": "craft cocktails, sunset views of the river, oysters on the half shell", "ambience": ["trendy", "classy"],
     "meals": ["dinner"], "hours": NIGHT, "alcohol": "full_bar", "noise": "average", "wifi": "free", "near": ["CBD", "French Quarter"],
     "names": ["Eleven Stories Rooftop", "Gaslight Cocktail Parlor", "Skyline Sazerac", "Copper Still Bar"]},
    {"cuisine": "special occasion steakhouse", "categories": "Steakhouses, American (Traditional), Restaurants", "price": 4,
     "dishes": "dry-aged ribeye, creamed spinach, bread pudding", "ambience": ["upscale", "classy", "romantic"],
     "meals": ["dinner"], "hours": DINNER, "alcohol": "full_bar", "noise": "average", "wifi": "no", "reservations": True,
     "names": ["Ironwood Chophouse", "Canal Street Prime", "Red Brick Steak Room"]},
    {"cuisine": "French fine dining with a tasting menu", "categories": "French, Restaurants", "price": 4,
     "dishes": "seven-course tasting menu, wine pairing, duck confit", "ambience": ["upscale", "romantic", "intimate"],
     "meals": ["dinner"], "hours": DINNER, "alcohol": "full_bar", "noise": "quiet", "wifi": "no", "reservations": True,
     "names": ["Maison Lumière", "Atelier Garance", "Petit Jardin"]},
    {"cuisine": "vegan and vegetarian kitchen", "categories": "Vegan, Vegetarian, Restaurants", "price": 2,
     "dishes": "vegan po-boys, jackfruit tacos, grain bowls, smoothies", "ambience": ["casual", "hipster"],
     "meals": ["lunch", "dinner"], "hours": LUNCH_DINNER, "alcohol": "none", "noise": "quiet", "wifi": "free",
     "names": ["Green Parade", "Okra & Root", "Sprout Social"]},
    {"cuisine": "beignet and coffee stand", "categories": "Bakeries, Coffee & Tea, Desserts, Restaurants", "price": 1,
     "dishes": "beignets covered in powdered sugar, café au lait", "ambience": ["touristy", "casual"],
     "meals": ["breakfast", "dessert"], "hours": CAFE, "alcohol": "none", "noise": "loud", "wifi": "no",
     "names": ["Powdered Sugar Stand", "Belle Beignet", "Praline Morning"]},
    {"cuisine": "late night dive bar with burgers", "categories": "Burgers, Dive Bars, Bars, Restaurants", "price": 1,
     "dishes": "smash burgers, cheese fries, cheap beer, jukebox", "ambience": ["divey"], "meals": ["latenight"],
     "music": ["jukebox"], "hours": LATE, "alcohol": "full_bar", "noise": "loud", "wifi": "no",
     "names": ["Graveyard Shift Grill", "Smoky Jukebox Burgers", "Dive & Dine", "Last Call Patty Shack"]},
    {"cuisine": "sushi bar", "categories": "Sushi Bars, Japanese, Restaurants", "price": 2,
     "dishes": "omakase, crawfish roll, spicy tuna, miso soup", "ambience": ["trendy"], "meals": ["lunch", "dinner"],
     "hours": LUNCH_DINNER, "alcohol": "beer_and_wine", "noise": "average", "wifi": "free",
     "names": ["Koi Pond Sushi", "Umami Levee", "Hana Bayou Sushi"]},
    {"cuisine": "taqueria", "categories": "Tacos, Mexican, Restaurants", "price": 1,
     "dishes": "al pastor tacos, birria, horchata, margaritas", "ambience": ["casual"], "meals": ["lunch", "dinner"],
     "hours": LUNCH_DINNER, "alcohol": "full_bar", "noise": "average", "wifi": "no", "outdoor": True,
     "names": ["Taqueria Calle Crescent", "Tamale Trolley", "Agave Bywater"]},
    {"cuisine": "Vietnamese pho and banh mi", "categories": "Vietnamese, Noodles, Restaurants", "price": 1,
     "dishes": "beef pho, banh mi, spring rolls, Vietnamese iced coffee", "ambience": ["casual"], "meals": ["lunch", "dinner"],
     "hours": LUNCH_DINNER, "alcohol": "none", "noise": "average", "wifi": "free",
     "names": ["Pho Bayou", "Banh Mi Boulevard", "Saigon Streetcar"]},
    {"cuisine": "barbecue joint", "categories": "Barbeque, Southern, Restaurants", "price": 2,
     "dishes": "smoked brisket, ribs, mac and cheese, sweet tea", "ambience": ["casual"], "meals": ["lunch", "dinner"],
     "hours": LUNCH_DINNER, "alcohol": "beer_and_wine", "noise": "average", "wifi": "no", "outdoor": True, "dogs": True,
     "kids": True, "names": ["Hickory Levee BBQ", "Smoke & Satsuma", "Pit Stop Smokehouse"]},
    {"cuisine": "family friendly neighborhood restaurant with a patio", "categories": "American (Traditional), Burgers, Restaurants",
     "price": 2, "dishes": "burgers, fried chicken, kids menu, big patio", "ambience": ["casual"], "meals": ["lunch", "dinner"],
     "hours": LUNCH_DINNER, "alcohol": "full_bar", "noise": "average", "wifi": "free", "outdoor": True, "dogs": True,
     "kids": True, "names": ["Porch Light Café", "Satsuma Tree Patio", "Neighborhood Noodle & Burger"]},
]

SYSTEM = """You write realistic, varied customer reviews for a fictional restaurant used in a software demo.
Write like different real customers: different lengths (one to three sentences), tones and details.
Mention specific dishes, service, prices, atmosphere and the neighborhood. Include a few mixed or negative reviews.
Never mention that the restaurant is fictional."""


def _id(rng: random.Random) -> str:
    return "".join(rng.choice(string.ascii_letters + string.digits + "-_") for _ in range(22))


def _dict(values: dict, rng: random.Random) -> str:
    prefix = "u" if rng.random() < 0.3 else ""
    return "{" + ", ".join(f"{prefix}'{k}': {v}" for k, v in values.items()) + "}"


def _attributes(p: dict, rng: random.Random) -> dict:
    quote = lambda v: f"u'{v}'" if rng.random() < 0.5 else f"'{v}'"
    flag = lambda v: "True" if v else "False"
    ambience = {a: a in p["ambience"] for a in ("touristy", "hipster", "romantic", "divey", "intimate", "trendy", "upscale", "classy", "casual")}
    meals = {m: m in p["meals"] for m in ("dessert", "latenight", "lunch", "dinner", "brunch", "breakfast")}
    attrs = {
        "RestaurantsPriceRange2": str(p["price"]),
        "WiFi": quote(p["wifi"]),
        "Alcohol": quote(p["alcohol"]),
        "NoiseLevel": quote(p["noise"]),
        "RestaurantsAttire": quote("dressy" if p["price"] == 4 else "casual"),
        "RestaurantsReservations": flag(p.get("reservations", False)),
        "OutdoorSeating": flag(p.get("outdoor", rng.random() < 0.4)),
        "GoodForKids": flag(p.get("kids", p["price"] <= 2 and rng.random() < 0.6)),
        "RestaurantsGoodForGroups": flag(rng.random() < 0.7),
        "DogsAllowed": flag(p.get("dogs", False)),
        "HappyHour": flag(p["alcohol"] == "full_bar" and rng.random() < 0.5),
        "RestaurantsTakeOut": "True",
        "Ambience": _dict(ambience, rng),
        "GoodForMeal": _dict(meals, rng),
        "BusinessParking": _dict({"garage": False, "street": True, "validated": False, "lot": rng.random() < 0.3, "valet": p["price"] >= 3}, rng),
    }
    if p.get("music"):
        attrs["Music"] = _dict({m: m in p["music"] for m in ("dj", "background_music", "jukebox", "live", "video", "karaoke")}, rng)
    if rng.random() < 0.08:
        del attrs["RestaurantsPriceRange2"]
    return attrs


def _businesses(rng: random.Random) -> list[dict]:
    businesses = []
    for p in PROFILES:
        for name in p["names"]:
            area = rng.choice(p.get("near") or list(search.NEIGHBORHOODS))
            lat, lon = search.NEIGHBORHOODS[area]
            hours = dict(p["hours"])
            if rng.random() < 0.1:
                hours["Monday"] = "0:0-0:0"
            businesses.append({
                "business_id": _id(rng), "name": name,
                "address": f"{rng.randint(100, 4999)} {rng.choice(STREETS[area])}",
                "city": rng.choice(["New Orleans"] * 12 + ["NEW ORLEANS", "new orleans"]), "state": "LA",
                "postal_code": rng.choice(["70112", "70116", "70117", "70130", "70115", "70119"]),
                "latitude": round(lat + rng.uniform(-0.008, 0.008), 6), "longitude": round(lon + rng.uniform(-0.008, 0.008), 6),
                "stars": 0, "review_count": 0, "is_open": 1, "attributes": _attributes(p, rng),
                "categories": p["categories"], "hours": None if rng.random() < 0.05 else hours,
                "_profile": p, "_area": area,
            })
    for i, (city, open_, categories) in enumerate([
        ("Metairie", 1, "Seafood, Restaurants"), ("Kenner", 1, "Pizza, Restaurants"),
        ("New Orleans", 0, "Cajun/Creole, Restaurants"), ("New Orleans", 1, "Books, Shopping"),
    ]):
        businesses.append({
            "business_id": _id(rng), "name": f"Out of Scope Business {i + 1}", "address": "1 Example St", "city": city,
            "state": "LA", "postal_code": "70001", "latitude": 29.98, "longitude": -90.15, "stars": 4.0, "review_count": 30,
            "is_open": open_, "attributes": None, "categories": categories, "hours": None,
        })
    return businesses


def _reviews_for(b: dict) -> list[dict]:
    p = b["_profile"]
    user = (f"Restaurant: {b['name']}, a {p['cuisine']} in the {b['_area']} area of New Orleans.\n"
            f"Known for: {p['dishes']}. Price level: {'$' * p['price']}. Vibe: {', '.join(p['ambience'])}.\n"
            f"Write {REVIEWS_PER_RESTAURANT} reviews. Most are 4 or 5 stars, some 3, one or two 1 or 2 stars.")
    schema = {
        "type": "object",
        "properties": {"reviews": {
            "type": "array", "minItems": REVIEWS_PER_RESTAURANT, "maxItems": REVIEWS_PER_RESTAURANT,
            "items": {"type": "object", "properties": {"stars": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
                                                        "text": {"type": "string"}},
                      "required": ["stars", "text"], "additionalProperties": False},
        }},
        "required": ["reviews"], "additionalProperties": False,
    }
    return llm.complete_json(SYSTEM, user, schema, max_tokens=4096, temperature=0.8).output["reviews"]


def main() -> None:
    if not llm.status()["enabled"]:
        raise SystemExit(f"LLM required to write the demo reviews: {llm.status()['reason']}")
    rng = random.Random(SEED)
    businesses = _businesses(rng)
    restaurants = [b for b in businesses if "_profile" in b]
    print(f"writing reviews for {len(restaurants)} fictional restaurants with {llm.status()['model']} ...")

    config.LLM_TIMEOUT = 600
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    cache = {}
    if CACHE_FILE.exists():
        cache = {row["name"]: row["reviews"] for row in map(json.loads, CACHE_FILE.read_text().splitlines())}
    t0 = time.time()
    lock = Lock()

    def generate(b):
        if b["name"] in cache:
            return cache[b["name"]]
        for _ in range(3):
            try:
                reviews = _reviews_for(b)
                break
            except llm.LLMError as e:
                print(f"  retrying {b['name']} ({e})")
        else:
            raise SystemExit(f"could not generate reviews for {b['name']}")
        with lock:
            cache[b["name"]] = reviews
            with open(CACHE_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps({"name": b["name"], "reviews": reviews}, ensure_ascii=False) + "\n")
            print(f"  {len(cache)}/{len(restaurants)} {b['name']} ({len(reviews)} reviews, {time.time() - t0:.0f}s)")
        return reviews

    with ThreadPoolExecutor(WORKERS) as pool:
        texts = list(pool.map(generate, restaurants))

    reviews = []
    start = datetime(2017, 1, 1)
    for b, generated in zip(restaurants, texts):
        if rng.random() < 0.15:
            generated = generated + [{"stars": 5, "text": "Good."}]
        for r in generated:
            reviews.append({
                "review_id": _id(rng), "user_id": _id(rng), "business_id": b["business_id"], "stars": float(r["stars"]),
                "useful": int(rng.expovariate(0.4)), "funny": int(rng.expovariate(1.0)), "cool": int(rng.expovariate(0.8)),
                "text": r["text"].strip(),
                "date": (start + timedelta(minutes=rng.randint(0, 5 * 365 * 24 * 60))).strftime("%Y-%m-%d %H:%M:%S"),
            })
        stars = [r["stars"] for r in generated]
        b["stars"] = round(sum(stars) / len(stars) * 2) / 2
        b["review_count"] = len(generated) + rng.randint(0, 6)

    with open(DEMO_DIR / "yelp_academic_dataset_business.json", "w", encoding="utf-8") as f:
        for b in businesses:
            f.write(json.dumps({k: v for k, v in b.items() if not k.startswith("_")}, ensure_ascii=False) + "\n")
    with open(DEMO_DIR / "yelp_academic_dataset_review.json", "w", encoding="utf-8") as f:
        for r in reviews:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    CACHE_FILE.unlink()
    print(f"wrote {len(businesses)} businesses and {len(reviews)} reviews to {DEMO_DIR} in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
