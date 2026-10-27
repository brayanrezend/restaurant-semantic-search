CREATE TABLE IF NOT EXISTS etl_batch (
  batch_id       NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  source_name    VARCHAR2(30)   NOT NULL,
  source_file    VARCHAR2(400)  NOT NULL,
  file_sha256    VARCHAR2(64)   NOT NULL,
  extract_filter VARCHAR2(400),
  status         VARCHAR2(10)   NOT NULL CHECK (status IN ('RUNNING', 'SUCCESS', 'FAILED')),
  rows_read      NUMBER,
  rows_loaded    NUMBER,
  error_message  VARCHAR2(4000),
  started_at     TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
  finished_at    TIMESTAMP
);

CREATE TABLE IF NOT EXISTS raw_business (
  batch_id  NUMBER NOT NULL REFERENCES etl_batch,
  line_no   NUMBER NOT NULL,
  doc       JSON   NOT NULL,
  loaded_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
  CONSTRAINT raw_business_pk PRIMARY KEY (batch_id, line_no)
);

CREATE TABLE IF NOT EXISTS raw_review (
  batch_id  NUMBER NOT NULL REFERENCES etl_batch,
  line_no   NUMBER NOT NULL,
  doc       JSON   NOT NULL,
  loaded_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
  CONSTRAINT raw_review_pk PRIMARY KEY (batch_id, line_no)
);
