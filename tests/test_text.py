from rss.pipeline.docs import DOC_BUDGET, FLAGS, build_doc
from rss.pipeline.passages import MAX_CHARS, split_passages


def restaurant(**values):
    base = {"name": "Test Kitchen", "price_level": 2, "noise_level": "quiet", "attire": "casual", "wifi": "free",
            "alcohol": "full_bar"} | {flag: False for flag in FLAGS}
    return base | values


def test_build_doc_profile_and_generic_categories():
    doc, used = build_doc(restaurant(outdoor_seating=True), ["Restaurants", "Food", "Italian"],
                          {"ambience": ["romantic"]}, [("r1", "Great pasta.")])
    assert doc.startswith("Test Kitchen. Italian in New Orleans.")
    assert "Moderately priced" in doc and "free WiFi" in doc and "outdoor seating" in doc
    assert "Ambience: romantic." in doc
    assert "Restaurants" not in doc
    assert used == ["r1"]


def test_build_doc_respects_budget_and_records_used_reviews():
    reviews = [(f"r{i}", "word " * 200) for i in range(20)]
    doc, used = build_doc(restaurant(), ["Pizza"], {}, reviews)
    assert len(doc) <= DOC_BUDGET
    assert 0 < len(used) < 20
    assert used == [f"r{i}" for i in range(len(used))]


def test_split_passages_filters_short_and_clips_long_sentences():
    text = "Too short. " + "This sentence is long enough to be a passage. " + ("x" * 10 + " ") * 60
    passages = split_passages(text)
    assert passages[0] == "This sentence is long enough to be a passage."
    assert all(len(p) <= MAX_CHARS + 1 for p in passages)
    assert passages[-1].endswith("…")
