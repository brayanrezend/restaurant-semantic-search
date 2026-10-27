CREATE OR REPLACE VIEW v_business_scope AS
SELECT business_id
FROM stg_business
WHERE city_norm = 'New Orleans'
  AND state = 'LA'
  AND is_open = 1
  AND categories LIKE '%Restaurants%';

CREATE OR REPLACE VIEW v_business_attributes_raw AS
SELECT b.business_id, a.*
FROM stg_business b
JOIN v_business_scope s ON s.business_id = b.business_id
OUTER APPLY JSON_TABLE(b.attributes, '$' COLUMNS (
  price_range     VARCHAR2(20)   PATH '$.RestaurantsPriceRange2',
  wifi            VARCHAR2(30)   PATH '$.WiFi',
  alcohol         VARCHAR2(30)   PATH '$.Alcohol',
  noise_level     VARCHAR2(30)   PATH '$.NoiseLevel',
  attire          VARCHAR2(30)   PATH '$.RestaurantsAttire',
  reservations    VARCHAR2(10)   PATH '$.RestaurantsReservations',
  outdoor_seating VARCHAR2(10)   PATH '$.OutdoorSeating',
  good_for_kids   VARCHAR2(10)   PATH '$.GoodForKids',
  good_for_groups VARCHAR2(10)   PATH '$.RestaurantsGoodForGroups',
  delivery        VARCHAR2(10)   PATH '$.RestaurantsDelivery',
  takeout         VARCHAR2(10)   PATH '$.RestaurantsTakeOut',
  has_tv          VARCHAR2(10)   PATH '$.HasTV',
  happy_hour      VARCHAR2(10)   PATH '$.HappyHour',
  dogs_allowed    VARCHAR2(10)   PATH '$.DogsAllowed',
  wheelchair      VARCHAR2(10)   PATH '$.WheelchairAccessible',
  table_service   VARCHAR2(10)   PATH '$.RestaurantsTableService',
  byob            VARCHAR2(10)   PATH '$.BYOB',
  ambience        VARCHAR2(1000) PATH '$.Ambience',
  good_for_meal   VARCHAR2(1000) PATH '$.GoodForMeal',
  music           VARCHAR2(1000) PATH '$.Music',
  parking         VARCHAR2(1000) PATH '$.BusinessParking'
)) a;

CREATE OR REPLACE VIEW v_business_attributes AS
SELECT business_id,
       TO_NUMBER(yelp_str(price_range) DEFAULT NULL ON CONVERSION ERROR) AS price_level,
       yelp_str(wifi)              AS wifi,
       yelp_str(alcohol)           AS alcohol,
       yelp_str(noise_level)       AS noise_level,
       yelp_str(attire)            AS attire,
       yelp_bool(reservations)     AS takes_reservations,
       yelp_bool(outdoor_seating)  AS outdoor_seating,
       yelp_bool(good_for_kids)    AS good_for_kids,
       yelp_bool(good_for_groups)  AS good_for_groups,
       yelp_bool(delivery)         AS delivery,
       yelp_bool(takeout)          AS takeout,
       yelp_bool(has_tv)           AS has_tv,
       yelp_bool(happy_hour)       AS happy_hour,
       yelp_bool(dogs_allowed)     AS dogs_allowed,
       yelp_bool(wheelchair)       AS wheelchair_accessible,
       yelp_bool(table_service)    AS table_service,
       yelp_bool(byob)             AS byob
FROM v_business_attributes_raw;

CREATE OR REPLACE VIEW v_business_tags AS
SELECT business_id, 'ambience' AS tag_group, tag
FROM (
  SELECT a.business_id, j.*
  FROM v_business_attributes_raw a,
       JSON_TABLE(yelp_dict_to_json(a.ambience), '$' COLUMNS (
         touristy VARCHAR2(5) PATH '$.touristy', hipster VARCHAR2(5) PATH '$.hipster',
         romantic VARCHAR2(5) PATH '$.romantic', divey   VARCHAR2(5) PATH '$.divey',
         intimate VARCHAR2(5) PATH '$.intimate', trendy  VARCHAR2(5) PATH '$.trendy',
         upscale  VARCHAR2(5) PATH '$.upscale',  classy  VARCHAR2(5) PATH '$.classy',
         casual   VARCHAR2(5) PATH '$.casual')) j
)
UNPIVOT (val FOR tag IN (touristy AS 'touristy', hipster AS 'hipster', romantic AS 'romantic', divey AS 'divey',
                         intimate AS 'intimate', trendy AS 'trendy', upscale AS 'upscale', classy AS 'classy',
                         casual AS 'casual'))
WHERE val = 'true'
UNION ALL
SELECT business_id, 'meal', tag
FROM (
  SELECT a.business_id, j.*
  FROM v_business_attributes_raw a,
       JSON_TABLE(yelp_dict_to_json(a.good_for_meal), '$' COLUMNS (
         dessert VARCHAR2(5) PATH '$.dessert', latenight VARCHAR2(5) PATH '$.latenight',
         lunch   VARCHAR2(5) PATH '$.lunch',   dinner    VARCHAR2(5) PATH '$.dinner',
         brunch  VARCHAR2(5) PATH '$.brunch',  breakfast VARCHAR2(5) PATH '$.breakfast')) j
)
UNPIVOT (val FOR tag IN (dessert AS 'dessert', latenight AS 'latenight', lunch AS 'lunch', dinner AS 'dinner',
                         brunch AS 'brunch', breakfast AS 'breakfast'))
WHERE val = 'true'
UNION ALL
SELECT business_id, 'music', tag
FROM (
  SELECT a.business_id, j.*
  FROM v_business_attributes_raw a,
       JSON_TABLE(yelp_dict_to_json(a.music), '$' COLUMNS (
         dj      VARCHAR2(5) PATH '$.dj',      background_music VARCHAR2(5) PATH '$.background_music',
         jukebox VARCHAR2(5) PATH '$.jukebox', live             VARCHAR2(5) PATH '$.live',
         video   VARCHAR2(5) PATH '$.video',   karaoke          VARCHAR2(5) PATH '$.karaoke')) j
)
UNPIVOT (val FOR tag IN (dj AS 'dj', background_music AS 'background_music', jukebox AS 'jukebox',
                         live AS 'live', video AS 'video', karaoke AS 'karaoke'))
WHERE val = 'true'
UNION ALL
SELECT business_id, 'parking', tag
FROM (
  SELECT a.business_id, j.*
  FROM v_business_attributes_raw a,
       JSON_TABLE(yelp_dict_to_json(a.parking), '$' COLUMNS (
         garage VARCHAR2(5) PATH '$.garage', street VARCHAR2(5) PATH '$.street',
         validated VARCHAR2(5) PATH '$.validated', lot VARCHAR2(5) PATH '$.lot',
         valet VARCHAR2(5) PATH '$.valet')) j
)
UNPIVOT (val FOR tag IN (garage AS 'garage', street AS 'street', validated AS 'validated', lot AS 'lot',
                         valet AS 'valet'))
WHERE val = 'true';

CREATE OR REPLACE VIEW v_business_hours AS
SELECT business_id, day_of_week, slot,
       CASE
         WHEN NOT REGEXP_LIKE(slot, '^\d{1,2}:\d{1,2}-\d{1,2}:\d{1,2}$') THEN 'INVALID'
         WHEN open_min = close_min THEN 'AMBIGUOUS'
         WHEN close_min < open_min THEN 'OVERNIGHT'
         ELSE 'NORMAL'
       END AS slot_status,
       open_min, close_min
FROM (
  SELECT business_id, day_of_week, slot,
         TO_NUMBER(REGEXP_SUBSTR(slot, '\d+', 1, 1)) * 60 + TO_NUMBER(REGEXP_SUBSTR(slot, '\d+', 1, 2)) AS open_min,
         TO_NUMBER(REGEXP_SUBSTR(slot, '\d+', 1, 3)) * 60 + TO_NUMBER(REGEXP_SUBSTR(slot, '\d+', 1, 4)) AS close_min
  FROM (
    SELECT b.business_id, h.*
    FROM stg_business b
    JOIN v_business_scope s ON s.business_id = b.business_id,
    JSON_TABLE(b.hours, '$' COLUMNS (
      d1 VARCHAR2(20) PATH '$.Monday',   d2 VARCHAR2(20) PATH '$.Tuesday',
      d3 VARCHAR2(20) PATH '$.Wednesday', d4 VARCHAR2(20) PATH '$.Thursday',
      d5 VARCHAR2(20) PATH '$.Friday',   d6 VARCHAR2(20) PATH '$.Saturday',
      d7 VARCHAR2(20) PATH '$.Sunday')) h
  )
  UNPIVOT (slot FOR day_of_week IN (d1 AS 1, d2 AS 2, d3 AS 3, d4 AS 4, d5 AS 5, d6 AS 6, d7 AS 7))
);

CREATE OR REPLACE VIEW v_dq_quarantine AS
SELECT DISTINCT table_name, record_key
FROM dq_result
WHERE severity = 'ERROR'
  AND run_id = (SELECT MAX(run_id) FROM dq_run WHERE status = 'SUCCESS');

CREATE OR REPLACE VIEW v_dq_summary AS
SELECT c.run_id, c.check_name, c.severity, c.failed_rows
FROM dq_check c
WHERE c.run_id = (SELECT MAX(run_id) FROM dq_run WHERE status = 'SUCCESS');

CREATE OR REPLACE VIEW v_restaurant_candidates AS
WITH review_counts AS (
  SELECT r.business_id, COUNT(*) AS review_count
  FROM stg_review r
  WHERE NOT EXISTS (SELECT 1 FROM v_dq_quarantine q WHERE q.table_name = 'stg_review' AND q.record_key = r.review_id)
  GROUP BY r.business_id
),
hours_status AS (
  SELECT business_id,
         CASE WHEN MAX(CASE WHEN slot_status IN ('AMBIGUOUS', 'INVALID') THEN 1 ELSE 0 END) = 1 THEN 'PARTIAL' ELSE 'OK' END AS hours_status
  FROM v_business_hours
  GROUP BY business_id
)
SELECT b.business_id, b.name, b.address, b.postal_code, b.latitude, b.longitude, b.stars,
       rc.review_count, b.review_count AS review_count_declared, b.categories,
       a.price_level, a.wifi, a.alcohol, a.noise_level, a.attire,
       a.takes_reservations, a.outdoor_seating, a.good_for_kids, a.good_for_groups, a.delivery, a.takeout,
       a.has_tv, a.happy_hour, a.dogs_allowed, a.wheelchair_accessible, a.table_service, a.byob,
       NVL(h.hours_status, 'MISSING') AS hours_status
FROM stg_business b
JOIN v_business_scope s ON s.business_id = b.business_id
JOIN review_counts rc ON rc.business_id = b.business_id
LEFT JOIN v_business_attributes a ON a.business_id = b.business_id
LEFT JOIN hours_status h ON h.business_id = b.business_id
WHERE rc.review_count >= 20
  AND NOT EXISTS (SELECT 1 FROM v_dq_quarantine q WHERE q.table_name = 'stg_business' AND q.record_key = b.business_id);
