CREATE TABLE IF NOT EXISTS cur_restaurant_doc (
  business_id VARCHAR2(22) PRIMARY KEY REFERENCES cur_restaurant ON DELETE CASCADE,
  doc_text    CLOB         NOT NULL,
  doc_hash    VARCHAR2(64) NOT NULL,
  review_ids  JSON,
  built_at    TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS cur_restaurant_embedding (
  business_id    VARCHAR2(22)  NOT NULL REFERENCES cur_restaurant ON DELETE CASCADE,
  model_name     VARCHAR2(100) NOT NULL,
  model_revision VARCHAR2(64)  NOT NULL,
  doc_hash       VARCHAR2(64)  NOT NULL,
  embedding      VECTOR(384, FLOAT32) NOT NULL,
  embedded_at    TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
  CONSTRAINT cur_restaurant_embedding_pk PRIMARY KEY (business_id, model_name)
);
