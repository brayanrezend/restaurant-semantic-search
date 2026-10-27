MERGE INTO stg_review t
USING (
  SELECT *
  FROM (
    SELECT r.batch_id, r.line_no, jt.*,
           ROW_NUMBER() OVER (PARTITION BY jt.review_id ORDER BY r.line_no DESC) AS rn
    FROM raw_review r,
         JSON_TABLE(r.doc, '$' ERROR ON ERROR COLUMNS (
           review_id   VARCHAR2(22) PATH '$.review_id',
           business_id VARCHAR2(22) PATH '$.business_id',
           user_id     VARCHAR2(22) PATH '$.user_id',
           stars       NUMBER       PATH '$.stars',
           useful      NUMBER       PATH '$.useful',
           funny       NUMBER       PATH '$.funny',
           cool        NUMBER       PATH '$.cool',
           review_text CLOB         PATH '$.text',
           review_date VARCHAR2(30) PATH '$.date'
         )) jt
    WHERE r.batch_id = (SELECT MAX(batch_id) FROM etl_batch WHERE source_name = 'review' AND status = 'SUCCESS')
  )
  WHERE rn = 1
) s
ON (t.review_id = s.review_id)
WHEN MATCHED THEN UPDATE SET
  t.business_id = s.business_id, t.user_id = s.user_id, t.stars = s.stars, t.useful = s.useful,
  t.funny = s.funny, t.cool = s.cool, t.review_text = s.review_text,
  t.review_date = TO_TIMESTAMP(s.review_date DEFAULT NULL ON CONVERSION ERROR, 'YYYY-MM-DD HH24:MI:SS'),
  t.batch_id = s.batch_id, t.line_no = s.line_no, t.updated_at = SYSTIMESTAMP
WHEN NOT MATCHED THEN INSERT (
  review_id, business_id, user_id, stars, useful, funny, cool, review_text, review_date, batch_id, line_no
) VALUES (
  s.review_id, s.business_id, s.user_id, s.stars, s.useful, s.funny, s.cool, s.review_text,
  TO_TIMESTAMP(s.review_date DEFAULT NULL ON CONVERSION ERROR, 'YYYY-MM-DD HH24:MI:SS'), s.batch_id, s.line_no
);

DELETE FROM stg_review
WHERE batch_id <> (SELECT MAX(batch_id) FROM etl_batch WHERE source_name = 'review' AND status = 'SUCCESS');
