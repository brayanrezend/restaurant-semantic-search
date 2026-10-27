CREATE INDEX IF NOT EXISTS stg_review_text_ix ON stg_review (review_text)
  INDEXTYPE IS CTXSYS.CONTEXT PARAMETERS ('SYNC (MANUAL)');

CREATE VECTOR INDEX IF NOT EXISTS cur_review_passage_hnsw ON cur_review_passage (embedding)
  ORGANIZATION INMEMORY NEIGHBOR GRAPH DISTANCE COSINE WITH TARGET ACCURACY 95;

CREATE TABLE IF NOT EXISTS eval_run (
  run_id          NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  experiment      VARCHAR2(30)  NOT NULL,
  variant         VARCHAR2(100) NOT NULL,
  model           VARCHAR2(100) NOT NULL,
  strategy        VARCHAR2(30)  NOT NULL,
  use_llm         BOOLEAN       NOT NULL,
  k               NUMBER        NOT NULL,
  queries         NUMBER        NOT NULL,
  precision_at_k  NUMBER,
  recall_at_k     NUMBER,
  mrr             NUMBER,
  ndcg_at_k       NUMBER,
  p50_ms          NUMBER,
  filter_accuracy NUMBER,
  invented_filters NUMBER,
  missed_filters  NUMBER,
  created_at      TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS eval_result (
  run_id         NUMBER       NOT NULL REFERENCES eval_run ON DELETE CASCADE,
  query_id       VARCHAR2(50) NOT NULL,
  relevant_count NUMBER       NOT NULL,
  hits           NUMBER       NOT NULL,
  precision_at_k NUMBER,
  recall_at_k    NUMBER,
  rr             NUMBER,
  ndcg_at_k      NUMBER,
  latency_ms     NUMBER,
  details        JSON,
  CONSTRAINT eval_result_pk PRIMARY KEY (run_id, query_id)
);

CREATE TABLE IF NOT EXISTS ann_benchmark (
  run_id          NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  table_name      VARCHAR2(30) NOT NULL,
  vectors         NUMBER       NOT NULL,
  target_accuracy NUMBER       NOT NULL,
  k               NUMBER       NOT NULL,
  queries         NUMBER       NOT NULL,
  recall_vs_exact NUMBER       NOT NULL,
  exact_p50_ms    NUMBER       NOT NULL,
  exact_p95_ms    NUMBER       NOT NULL,
  approx_p50_ms   NUMBER       NOT NULL,
  approx_p95_ms   NUMBER       NOT NULL,
  approx_plan     VARCHAR2(200),
  created_at      TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);
