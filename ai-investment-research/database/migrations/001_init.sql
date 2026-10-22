-- 001_init.sql — AI Investment Research MVP 階段 A
-- 目標：PostgreSQL 15+（含 Supabase）。可重複執行（IF NOT EXISTS）。
--
-- 設計原則：
--   * 外部資料表一律保存 source / fetched_at / data_status。
--   * 抓取失敗只寫入 data_fetch_log（status = 'error'）；資料表不存放任何替代或虛構數值。
--   * 所有表啟用 RLS 且不建立 policy：anon / authenticated 無法直接存取，
--     後端以 service role 或資料庫連線（皆繞過 RLS）存取。

BEGIN;

-- 標的。名稱等外部取得的欄位一旦存在，就必須有來源、時間與狀態。
CREATE TABLE IF NOT EXISTS instruments (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    market        text NOT NULL CHECK (market IN ('TW', 'US', 'MACRO')),
    symbol        text NOT NULL,
    name          text,
    currency      text,
    exchange      text,
    source        text,
    source_url    text,
    fetched_at    timestamptz,
    data_status   text CHECK (data_status IN ('ok', 'stale', 'partial')),
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (market, symbol),
    CHECK (name IS NULL OR (source IS NOT NULL AND fetched_at IS NOT NULL AND data_status IS NOT NULL))
);

-- 觀察清單（使用者自己的資料，非外部資料）。
CREATE TABLE IF NOT EXISTS watchlist (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    instrument_id uuid NOT NULL UNIQUE REFERENCES instruments(id) ON DELETE CASCADE,
    note          text,
    is_active     boolean NOT NULL DEFAULT true,
    added_at      timestamptz NOT NULL DEFAULT now()
);

-- 行情（日 K）。不合理的價格由 CHECK 拒絕，並應記入 data_fetch_log。
CREATE TABLE IF NOT EXISTS price_bars (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    instrument_id   uuid NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
    trade_date      date NOT NULL,
    open            numeric(18, 4) NOT NULL,
    high            numeric(18, 4) NOT NULL,
    low             numeric(18, 4) NOT NULL,
    close           numeric(18, 4) NOT NULL,
    volume          bigint CHECK (volume >= 0),
    adjusted_close  numeric(18, 4),
    source          text NOT NULL,
    source_url      text,
    fetched_at      timestamptz NOT NULL,
    data_status     text NOT NULL CHECK (data_status IN ('ok', 'stale', 'partial')),
    created_at      timestamptz NOT NULL DEFAULT now(),
    CHECK (low > 0 AND high >= low AND high >= open AND high >= close AND low <= open AND low <= close),
    UNIQUE (instrument_id, trade_date, source)
);

-- 財報。line_items 保存來源原始科目與數值，不做補值。
CREATE TABLE IF NOT EXISTS financial_statements (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    instrument_id   uuid NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
    period_type     text NOT NULL CHECK (period_type IN ('Q', 'Y')),
    fiscal_year     integer NOT NULL,
    fiscal_quarter  smallint NOT NULL DEFAULT 0,
    period_end      date NOT NULL,
    statement_type  text NOT NULL CHECK (statement_type IN ('income', 'balance', 'cashflow')),
    line_items      jsonb NOT NULL,
    currency        text,
    unit            text,
    published_at    timestamptz,
    source          text NOT NULL,
    source_url      text,
    fetched_at      timestamptz NOT NULL,
    data_status     text NOT NULL CHECK (data_status IN ('ok', 'stale', 'partial')),
    created_at      timestamptz NOT NULL DEFAULT now(),
    CHECK (
        (period_type = 'Y' AND fiscal_quarter = 0)
        OR (period_type = 'Q' AND fiscal_quarter BETWEEN 1 AND 4)
    ),
    UNIQUE (instrument_id, period_type, fiscal_year, fiscal_quarter, statement_type, source)
);

-- 外部資料抓取紀錄與錯誤紀錄。
CREATE TABLE IF NOT EXISTS data_fetch_log (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source          text NOT NULL,
    endpoint        text,
    instrument_id   uuid REFERENCES instruments(id) ON DELETE SET NULL,
    request_params  jsonb,
    status          text NOT NULL CHECK (status IN ('ok', 'partial', 'error', 'skipped')),
    http_status     integer,
    error_type      text,
    error_message   text,
    rows_fetched    integer,
    started_at      timestamptz NOT NULL,
    finished_at     timestamptz,
    CHECK (status <> 'error' OR error_type IS NOT NULL)
);

-- 研究執行紀錄：保存當次快照、模型、提示詞版本與最終裁決。
CREATE TABLE IF NOT EXISTS research_runs (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    instrument_id    uuid NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
    triggered_by     text NOT NULL DEFAULT 'manual' CHECK (triggered_by IN ('manual', 'scheduled')),
    status           text NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending', 'running', 'completed', 'partial', 'failed')),
    snapshot         jsonb,
    snapshot_hash    text,
    llm_provider     text,
    llm_model        text,
    prompt_versions  jsonb,
    adjudication     jsonb,
    error_type       text,
    error_message    text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    started_at       timestamptz,
    finished_at      timestamptz,
    CHECK (status <> 'failed' OR error_type IS NOT NULL)
);

-- 辯論訊息：每個角色每階段一筆。無效輸出也保留原文與錯誤，不靜默丟棄。
-- bull / bear 的 initial 階段不得看過任何角色輸出，由 CHECK 在資料庫層強制。
CREATE TABLE IF NOT EXISTS debate_messages (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id             uuid NOT NULL REFERENCES research_runs(id) ON DELETE CASCADE,
    seq                integer NOT NULL,
    role               text NOT NULL
                       CHECK (role IN ('macro', 'fundamental', 'technical', 'bull', 'bear', 'adjudicator')),
    phase              text NOT NULL CHECK (phase IN ('initial', 'rebuttal', 'adjudication')),
    seen_roles         text[] NOT NULL DEFAULT '{}',
    content            jsonb,
    raw_response       text,
    validation_status  text NOT NULL CHECK (validation_status IN ('valid', 'invalid')),
    validation_error   text,
    llm_model          text,
    input_tokens       integer,
    output_tokens      integer,
    created_at         timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, seq),
    CHECK (NOT (role IN ('bull', 'bear') AND phase = 'initial') OR cardinality(seen_roles) = 0),
    CHECK ((role = 'adjudicator') = (phase = 'adjudication')),
    CHECK (validation_status <> 'valid' OR content IS NOT NULL),
    CHECK (validation_status <> 'invalid' OR validation_error IS NOT NULL)
);

-- 預測紀錄：供後續追蹤命中率。參考價必須帶來源與時間。
CREATE TABLE IF NOT EXISTS predictions (
    id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id                  uuid NOT NULL REFERENCES research_runs(id) ON DELETE CASCADE,
    instrument_id           uuid NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
    made_at                 timestamptz NOT NULL DEFAULT now(),
    horizon_days            integer NOT NULL CHECK (horizon_days > 0),
    verdict                 text NOT NULL
                            CHECK (verdict IN ('bullish_conditional', 'bearish_conditional', 'watch', 'insufficient_evidence')),
    reference_price         numeric(18, 4) NOT NULL CHECK (reference_price > 0),
    reference_price_source  text NOT NULL,
    reference_price_as_of   timestamptz NOT NULL,
    scenarios               jsonb,
    conditions              jsonb,
    invalidation            jsonb,
    status                  text NOT NULL DEFAULT 'open'
                            CHECK (status IN ('open', 'hit', 'missed', 'invalidated', 'expired')),
    resolved_at             timestamptz,
    resolved_price          numeric(18, 4),
    resolution_note         text,
    CHECK (status = 'open' OR resolved_at IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_price_bars_instrument_date ON price_bars (instrument_id, trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_financials_instrument_period ON financial_statements (instrument_id, period_end DESC);
CREATE INDEX IF NOT EXISTS idx_fetch_log_source_started ON data_fetch_log (source, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_instrument_created ON research_runs (instrument_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_debate_run ON debate_messages (run_id, seq);
CREATE INDEX IF NOT EXISTS idx_predictions_instrument_status ON predictions (instrument_id, status);

ALTER TABLE instruments            ENABLE ROW LEVEL SECURITY;
ALTER TABLE watchlist              ENABLE ROW LEVEL SECURITY;
ALTER TABLE price_bars             ENABLE ROW LEVEL SECURITY;
ALTER TABLE financial_statements   ENABLE ROW LEVEL SECURITY;
ALTER TABLE data_fetch_log         ENABLE ROW LEVEL SECURITY;
ALTER TABLE research_runs          ENABLE ROW LEVEL SECURITY;
ALTER TABLE debate_messages        ENABLE ROW LEVEL SECURITY;
ALTER TABLE predictions            ENABLE ROW LEVEL SECURITY;

COMMIT;
