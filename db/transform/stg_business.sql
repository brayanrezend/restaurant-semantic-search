MERGE INTO stg_business t
USING (
  SELECT *
  FROM (
    SELECT r.batch_id, r.line_no, jt.*,
           ROW_NUMBER() OVER (PARTITION BY jt.business_id ORDER BY r.line_no DESC) AS rn
    FROM raw_business r,
         JSON_TABLE(r.doc, '$' ERROR ON ERROR COLUMNS (
           business_id  VARCHAR2(22)   PATH '$.business_id',
           name         VARCHAR2(400)  PATH '$.name',
           address      VARCHAR2(400)  PATH '$.address',
           city         VARCHAR2(100)  PATH '$.city',
           state        VARCHAR2(10)   PATH '$.state',
           postal_code  VARCHAR2(20)   PATH '$.postal_code',
           latitude     NUMBER         PATH '$.latitude',
           longitude    NUMBER         PATH '$.longitude',
           stars        NUMBER         PATH '$.stars',
           review_count NUMBER         PATH '$.review_count',
           is_open      NUMBER         PATH '$.is_open',
           categories   VARCHAR2(4000) PATH '$.categories',
           attributes   JSON           PATH '$.attributes',
           hours        JSON           PATH '$.hours'
         )) jt
    WHERE r.batch_id = (SELECT MAX(batch_id) FROM etl_batch WHERE source_name = 'business' AND status = 'SUCCESS')
  )
  WHERE rn = 1
) s
ON (t.business_id = s.business_id)
WHEN MATCHED THEN UPDATE SET
  t.name = s.name, t.address = s.address, t.city = s.city, t.city_norm = INITCAP(TRIM(s.city)),
  t.state = s.state, t.postal_code = s.postal_code, t.latitude = s.latitude, t.longitude = s.longitude,
  t.stars = s.stars, t.review_count = s.review_count, t.is_open = s.is_open, t.categories = s.categories,
  t.attributes = s.attributes, t.hours = s.hours, t.batch_id = s.batch_id, t.line_no = s.line_no,
  t.updated_at = SYSTIMESTAMP
WHEN NOT MATCHED THEN INSERT (
  business_id, name, address, city, city_norm, state, postal_code, latitude, longitude,
  stars, review_count, is_open, categories, attributes, hours, batch_id, line_no
) VALUES (
  s.business_id, s.name, s.address, s.city, INITCAP(TRIM(s.city)), s.state, s.postal_code, s.latitude, s.longitude,
  s.stars, s.review_count, s.is_open, s.categories, s.attributes, s.hours, s.batch_id, s.line_no
);

DELETE FROM stg_business
WHERE batch_id <> (SELECT MAX(batch_id) FROM etl_batch WHERE source_name = 'business' AND status = 'SUCCESS');
