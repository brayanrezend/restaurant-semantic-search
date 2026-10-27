import pytest

from rss import assistant

CATEGORIES = ["Bars", "Burgers", "Pizza", "Sushi Bars", "Thai", "Tacos", "Cafes", "Barbeque", "Seafood", "Coffee & Tea"]


def raw(**values):
    base = {"semantic_query": "", "price_max": None, "min_stars": None, "category": None, "free_wifi": False,
            "open_now": False, "near": None, "tags": [], "features": []}
    return base | values


def active(filters):
    return {k: v for k, v in filters.items() if v not in (None, [], False)}


def test_willing_to_spend_more_is_not_a_price_ceiling():
    parsed, dropped = assistant._validate_parse(
        raw(semantic_query="hamburger", price_max=2, category="Bars"),
        "I want to eat a hamburger, and I'm willing to spend a bit more money.", CATEGORIES)
    assert active(parsed["filters"]) == {}
    assert dropped == 2


def test_cheap_burger_in_portuguese_keeps_price_and_drops_wrong_category():
    parsed, _ = assistant._validate_parse(
        raw(semantic_query="hamburger", price_max=1, category="Bars"), "hambúrguer bom e barato", CATEGORIES)
    assert active(parsed["filters"]) == {"price_max": 1}


def test_invented_filters_are_dropped():
    parsed, dropped = assistant._validate_parse(
        raw(semantic_query="lunch", open_now=True, tags=["live"], features=["dogs_allowed", "good_for_kids"]),
        "family friendly lunch spot with kids", CATEGORIES)
    assert active(parsed["filters"]) == {"features": ["good_for_kids"]}
    assert dropped == 3


def test_values_outside_the_allowed_lists_are_dropped():
    parsed, dropped = assistant._validate_parse(
        raw(category="Gastropubs", near="Atlantis", tags=["sleepy"], min_stars=3), "top rated gumbo", CATEGORIES)
    assert active(parsed["filters"]) == {}
    assert dropped == 4


def test_guard_words_match_word_starts_only():
    parsed, _ = assistant._validate_parse(raw(tags=["live", "romantic"]), "pizza delivery for an update", CATEGORIES)
    assert parsed["filters"]["tags"] == []


@pytest.mark.parametrize("category,text,expected", [
    ("Bars", "hamburguer bom e barato hamburger", False),
    ("Burgers", "hamburguer bom e barato hamburger", True),
    ("Bars", "cocktail bar downtown", True),
    ("Sushi Bars", "top rated sushi", True),
    ("Thai", "thai food", True),
    ("Tacos", "street tacos", True),
    ("Cafes", "quiet cafe", True),
    ("Barbeque", "barbecue ribs", True),
    ("Coffee & Tea", "coffee", True),
    ("Pizza", "best gumbo", False),
])
def test_category_must_appear_in_the_request(category, text, expected):
    assert assistant._category_grounded(category, text) is expected


@pytest.mark.parametrize("question,language", [
    ("I want to have pizza for lunch, but I want to spend very little.", "English"),
    ("Eu quero comer uma pizza mas quero gastar pouco", "Portuguese"),
    ("jantar romântico no French Quarter", "Portuguese"),
    ("pizza", "the same language as the request"),
])
def test_language_detection(question, language):
    assert assistant._language(question) == language


def test_hours_text():
    assert assistant._hours_text(None) == "unknown"
    assert assistant._hours_text({d: "11:00-22:00" for d in range(1, 8)}) == "daily 11:00-22:00"
    text = assistant._hours_text({2: "11:00-22:00", 3: "unclear"})
    assert text.startswith("Mon closed, Tue 11:00-22:00, Wed unclear")
