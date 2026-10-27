CREATE TABLE IF NOT EXISTS cur_review_passage (
  business_id    VARCHAR2(22)   NOT NULL REFERENCES cur_restaurant ON DELETE CASCADE,
  review_id      VARCHAR2(22)   NOT NULL,
  passage_no     NUMBER         NOT NULL,
  passage_text   VARCHAR2(1000) NOT NULL,
  model_name     VARCHAR2(100)  NOT NULL,
  model_revision VARCHAR2(64)   NOT NULL,
  embedding      VECTOR(384, FLOAT32) NOT NULL,
  embedded_at    TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
  CONSTRAINT cur_review_passage_pk PRIMARY KEY (review_id, model_name, passage_no)
);

CREATE INDEX IF NOT EXISTS cur_review_passage_business_ix ON cur_review_passage (business_id, model_name);
