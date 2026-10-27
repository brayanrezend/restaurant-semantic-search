from datetime import datetime

import pytest

from rss import search
from rss.db import split_sql


def test_split_sql_separates_statements_and_skips_comments():
    text = """-- comment
CREATE TABLE a (id NUMBER);

INSERT INTO a VALUES (1);
"""
    assert split_sql(text) == ["CREATE TABLE a (id NUMBER)", "INSERT INTO a VALUES (1)"]


def test_split_sql_keeps_plsql_blocks_whole():
    text = """CREATE OR REPLACE FUNCTION f(p VARCHAR2) RETURN VARCHAR2 IS
BEGIN
  RETURN p;
END;
/

CREATE OR REPLACE VIEW v AS SELECT 1 AS x FROM dual;
"""
    statements = split_sql(text)
    assert len(statements) == 2
    assert statements[0].endswith("END;")
    assert statements[1] == "CREATE OR REPLACE VIEW v AS SELECT 1 AS x FROM dual"


def test_build_sql_without_text_orders_by_rating_and_skips_vectors():
    sql, binds = search.build_sql(search.SearchRequest(price_max=1))
    assert "VECTOR_DISTANCE" not in sql
    assert "ORDER BY stars DESC" in sql
    assert binds == {"k": 10, "price_max": 1}


def test_build_sql_with_text_is_hybrid_with_all_filters():
    req = search.SearchRequest(text="pizza", category="Pizza", tags=["romantic"], features=["outdoor_seating"],
                               free_wifi=True, open_now=True, lat=29.95, lon=-90.07, radius_km=1)
    sql, binds = search.build_sql(req)
    assert "FETCH APPROX FIRST" in sql
    assert "WITH TARGET ACCURACY" in sql
    assert "r.outdoor_seating" in sql
    assert "r.wifi = 'free'" in sql
    assert "WHERE open_status = 'OPEN'" in sql
    assert binds["sdo_params"] == "distance=1 unit=KM"
    assert {"category", "tag0", "lat", "lon", "model"} <= binds.keys()


def test_build_sql_rejects_unknown_features():
    with pytest.raises(ValueError):
        search.build_sql(search.SearchRequest(features=["1=1; DROP TABLE x"]))


def test_clock_uses_new_orleans_time_and_previous_day():
    at, clock = search._clock(datetime(2022, 1, 17, 1, 30))
    assert at.utcoffset().total_seconds() == -6 * 3600
    assert clock == {"dow": 1, "prev_dow": 7, "minute": 90}


def test_terms_drop_stopwords():
    assert search._terms("I want a cheap pizza, willing to spend a bit more") == {"cheap", "pizza"}
