-- Additive migration; apply after 001_initial_schema.sql on PostgreSQL 13+.
BEGIN;

CREATE TABLE IF NOT EXISTS webhooks (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    endpoint_id UUID REFERENCES api_endpoints (id) ON DELETE CASCADE,
    url         TEXT NOT NULL,
    events      JSONB NOT NULL,
    enabled     BOOLEAN NOT NULL DEFAULT true,
    created_by  INTEGER REFERENCES users (id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_webhooks_events CHECK (
        jsonb_typeof(events) = 'array'
        AND jsonb_array_length(events) BETWEEN 1 AND 4
        AND events <@ '["call_success","call_failure","call_timeout","endpoint_created"]'::jsonb
    )
);

-- Null endpoint_id denotes a global subscription, never a deleted endpoint.
CREATE INDEX IF NOT EXISTS idx_webhooks_endpoint ON webhooks (endpoint_id);

DROP TRIGGER IF EXISTS trg_webhooks_updated_at ON webhooks;
CREATE TRIGGER trg_webhooks_updated_at
    BEFORE UPDATE ON webhooks
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Preserve existing indexes; add stable newest-first ordering for both views.
CREATE INDEX IF NOT EXISTS idx_api_call_logs_created_id
    ON api_call_logs (created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_api_call_logs_endpoint_created_id
    ON api_call_logs (endpoint_id, created_at DESC, id DESC);

COMMIT;
