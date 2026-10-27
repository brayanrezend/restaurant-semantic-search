INSERT INTO dq_result (run_id, check_name, severity, table_name, record_key, detail)
SELECT :run_id, 'duplicate_business_id', 'WARN', 'raw_business', r.doc.business_id.string(), COUNT(*) || ' lines'
FROM raw_business r
WHERE r.batch_id = (SELECT MAX(batch_id) FROM etl_batch WHERE source_name = 'business' AND status = 'SUCCESS')
GROUP BY r.doc.business_id.string()
HAVING COUNT(*) > 1;

INSERT INTO dq_result (run_id, check_name, severity, table_name, record_key, detail)
SELECT :run_id, 'city_name_normalized', 'INFO', 'stg_business', b.business_id, b.city || ' -> ' || b.city_norm
FROM stg_business b
WHERE b.state = 'LA' AND UPPER(b.city) LIKE '%ORLEANS%' AND b.city <> b.city_norm;

INSERT INTO dq_result (run_id, check_name, severity, table_name, record_key, detail)
SELECT :run_id, 'invalid_coordinates', 'ERROR', 'stg_business', b.business_id, b.latitude || ', ' || b.longitude
FROM stg_business b JOIN v_business_scope s ON s.business_id = b.business_id
WHERE b.latitude IS NULL OR b.longitude IS NULL
   OR b.latitude NOT BETWEEN 29.80 AND 30.20 OR b.longitude NOT BETWEEN -90.30 AND -89.60;

INSERT INTO dq_result (run_id, check_name, severity, table_name, record_key, detail)
SELECT :run_id, 'empty_name', 'ERROR', 'stg_business', b.business_id, NULL
FROM stg_business b JOIN v_business_scope s ON s.business_id = b.business_id
WHERE TRIM(b.name) IS NULL;

INSERT INTO dq_result (run_id, check_name, severity, table_name, record_key, detail)
SELECT :run_id, 'invalid_business_stars', 'ERROR', 'stg_business', b.business_id, TO_CHAR(b.stars)
FROM stg_business b JOIN v_business_scope s ON s.business_id = b.business_id
WHERE b.stars IS NULL OR b.stars NOT BETWEEN 1 AND 5;

INSERT INTO dq_result (run_id, check_name, severity, table_name, record_key, detail)
SELECT :run_id, 'empty_address', 'WARN', 'stg_business', b.business_id, b.name
FROM stg_business b JOIN v_business_scope s ON s.business_id = b.business_id
WHERE TRIM(b.address) IS NULL;

INSERT INTO dq_result (run_id, check_name, severity, table_name, record_key, detail)
SELECT :run_id, 'missing_hours', 'WARN', 'stg_business', s.business_id, NULL
FROM v_business_scope s
WHERE NOT EXISTS (SELECT 1 FROM v_business_hours h WHERE h.business_id = s.business_id);

INSERT INTO dq_result (run_id, check_name, severity, table_name, record_key, detail)
SELECT :run_id, 'ambiguous_hours', 'WARN', 'stg_business', h.business_id, 'day ' || h.day_of_week || ': ' || h.slot
FROM v_business_hours h
WHERE h.slot_status = 'AMBIGUOUS';

INSERT INTO dq_result (run_id, check_name, severity, table_name, record_key, detail)
SELECT :run_id, 'invalid_hours_format', 'WARN', 'stg_business', h.business_id, 'day ' || h.day_of_week || ': ' || h.slot
FROM v_business_hours h
WHERE h.slot_status = 'INVALID';

INSERT INTO dq_result (run_id, check_name, severity, table_name, record_key, detail)
SELECT :run_id, 'overnight_hours', 'INFO', 'stg_business', h.business_id, 'day ' || h.day_of_week || ': ' || h.slot
FROM v_business_hours h
WHERE h.slot_status = 'OVERNIGHT';

INSERT INTO dq_result (run_id, check_name, severity, table_name, record_key, detail)
SELECT :run_id, 'missing_price', 'WARN', 'stg_business', a.business_id, NULL
FROM v_business_attributes a
WHERE a.price_level IS NULL;

INSERT INTO dq_result (run_id, check_name, severity, table_name, record_key, detail)
SELECT :run_id, 'unparseable_attribute', 'WARN', 'stg_business', x.business_id, x.attr || ': ' || SUBSTR(x.val, 1, 200)
FROM v_business_attributes_raw a
UNPIVOT (val FOR attr IN (ambience AS 'Ambience', good_for_meal AS 'GoodForMeal', music AS 'Music', parking AS 'BusinessParking')) x
WHERE yelp_dict_to_json(x.val) IS NOT NULL AND yelp_dict_to_json(x.val) IS NOT JSON;

INSERT INTO dq_result (run_id, check_name, severity, table_name, record_key, detail)
SELECT :run_id, 'orphan_review', 'ERROR', 'stg_review', r.review_id, r.business_id
FROM stg_review r
WHERE NOT EXISTS (SELECT 1 FROM v_business_scope s WHERE s.business_id = r.business_id);

INSERT INTO dq_result (run_id, check_name, severity, table_name, record_key, detail)
SELECT :run_id, 'duplicate_review_id', 'WARN', 'raw_review', r.doc.review_id.string(), COUNT(*) || ' lines'
FROM raw_review r
WHERE r.batch_id = (SELECT MAX(batch_id) FROM etl_batch WHERE source_name = 'review' AND status = 'SUCCESS')
GROUP BY r.doc.review_id.string()
HAVING COUNT(*) > 1;

INSERT INTO dq_result (run_id, check_name, severity, table_name, record_key, detail)
SELECT :run_id, 'short_or_empty_review', 'ERROR', 'stg_review', r.review_id, TO_CHAR(DBMS_LOB.GETLENGTH(r.review_text)) || ' chars'
FROM stg_review r
WHERE r.review_text IS NULL OR DBMS_LOB.GETLENGTH(TRIM(r.review_text)) < 20;

INSERT INTO dq_result (run_id, check_name, severity, table_name, record_key, detail)
SELECT :run_id, 'invalid_review_stars', 'ERROR', 'stg_review', r.review_id, TO_CHAR(r.stars)
FROM stg_review r
WHERE r.stars IS NULL OR r.stars NOT BETWEEN 1 AND 5;

INSERT INTO dq_result (run_id, check_name, severity, table_name, record_key, detail)
SELECT :run_id, 'invalid_review_date', 'ERROR', 'stg_review', r.review_id, TO_CHAR(r.review_date)
FROM stg_review r
WHERE r.review_date IS NULL OR r.review_date < TIMESTAMP '2004-01-01 00:00:00' OR r.review_date > SYSTIMESTAMP;

INSERT INTO dq_result (run_id, check_name, severity, table_name, record_key, detail)
SELECT :run_id, 'review_count_below_declared', 'INFO', 'stg_business', b.business_id, rc.n || ' of ' || b.review_count
FROM stg_business b
JOIN (SELECT business_id, COUNT(*) AS n FROM stg_review GROUP BY business_id) rc ON rc.business_id = b.business_id
WHERE rc.n < b.review_count;
