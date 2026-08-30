-- LLM Gateway schema (Phase 1: DB & Auth Skeleton)
-- Applied automatically by the postgres image's docker-entrypoint-initdb.d
-- mechanism on first container start. See PLAN.md Section 4 for rationale
-- (single init.sql chosen over Alembic to keep the 30-hour scope simple).

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS api_keys (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key_hash             TEXT NOT NULL UNIQUE,
    label                TEXT NOT NULL,
    rate_limit_per_min   INTEGER,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    active               BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS request_logs (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    api_key_id           UUID REFERENCES api_keys(id) ON DELETE SET NULL,
    model_alias          TEXT,
    provider_used        TEXT,
    model_used           TEXT,
    status               TEXT,
    attempt_count        INTEGER,
    fallback_occurred    BOOLEAN,
    input_tokens         INTEGER,
    output_tokens        INTEGER,
    total_tokens         INTEGER,
    estimated_cost_usd   NUMERIC(12, 6),
    latency_ms           INTEGER,
    error_message        TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_request_logs_created_at ON request_logs (created_at);
CREATE INDEX IF NOT EXISTS idx_request_logs_api_key_id ON request_logs (api_key_id);
CREATE INDEX IF NOT EXISTS idx_request_logs_status ON request_logs (status);
