CREATE TABLE IF NOT EXISTS llm_cache (
  cache_key  VARCHAR2(64)  PRIMARY KEY,
  role       VARCHAR2(20)  NOT NULL,
  model      VARCHAR2(100) NOT NULL,
  output     JSON          NOT NULL,
  created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS llm_call (
  call_id       NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  role          VARCHAR2(20)   NOT NULL CHECK (role IN ('parse', 'explain')),
  provider      VARCHAR2(20)   NOT NULL,
  model         VARCHAR2(100)  NOT NULL,
  question      VARCHAR2(1000) NOT NULL,
  cache_hit     BOOLEAN        NOT NULL,
  success       BOOLEAN        NOT NULL,
  latency_ms    NUMBER,
  input_tokens  NUMBER,
  output_tokens NUMBER,
  dropped_items NUMBER,
  error_message VARCHAR2(1000),
  output        JSON,
  created_at    TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);
