CREATE TABLE IF NOT EXISTS dq_run (
  run_id      NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  status      VARCHAR2(10) NOT NULL CHECK (status IN ('RUNNING', 'SUCCESS', 'FAILED')),
  started_at  TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
  finished_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dq_check (
  run_id      NUMBER NOT NULL REFERENCES dq_run,
  check_name  VARCHAR2(60) NOT NULL,
  severity    VARCHAR2(5)  NOT NULL CHECK (severity IN ('ERROR', 'WARN', 'INFO')),
  failed_rows NUMBER NOT NULL,
  CONSTRAINT dq_check_pk PRIMARY KEY (run_id, check_name)
);

CREATE TABLE IF NOT EXISTS dq_result (
  run_id     NUMBER NOT NULL REFERENCES dq_run,
  check_name VARCHAR2(60)  NOT NULL,
  severity   VARCHAR2(5)   NOT NULL CHECK (severity IN ('ERROR', 'WARN', 'INFO')),
  table_name VARCHAR2(30)  NOT NULL,
  record_key VARCHAR2(100) NOT NULL,
  detail     VARCHAR2(1000)
);

CREATE INDEX IF NOT EXISTS dq_result_ix ON dq_result (run_id, table_name, severity, record_key);
