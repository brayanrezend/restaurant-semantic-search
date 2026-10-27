CREATE TABLE IF NOT EXISTS stg_review (
  review_id   VARCHAR2(22) PRIMARY KEY,
  business_id VARCHAR2(22) NOT NULL,
  user_id     VARCHAR2(22),
  stars       NUMBER(2,1),
  useful      NUMBER,
  funny       NUMBER,
  cool        NUMBER,
  review_text CLOB,
  review_date TIMESTAMP,
  batch_id    NUMBER NOT NULL,
  line_no     NUMBER NOT NULL,
  updated_at  TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS stg_review_business_ix ON stg_review (business_id);
