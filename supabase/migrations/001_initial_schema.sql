-- ============================================================================
-- API Mapper & Gateway — initial schema
-- Migration: 001_initial_schema.sql
-- Target:    PostgreSQL 13+ (Supabase compatible)
--
-- Creates the five core tables, supporting indexes, an updated_at trigger for
-- api_endpoints, and seeds the default roles + administrator
-- (admin@mapper.com / admin123 — CHANGE THIS PASSWORD AFTER FIRST LOGIN).
-- ============================================================================

-- gen_random_uuid() is built into PostgreSQL 13+; the extension keeps older
-- versions working as well.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ----------------------------------------------------------------------------
-- api_endpoints — one row per mapped endpoint (HTTP proxy, SFTP export, mock).
-- Credential columns (sftp_password, api_password) store AES-256-GCM
-- ciphertext produced by backend/core/crypto.py — never plaintext.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS api_endpoints (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    endpoint_code            VARCHAR(255) UNIQUE,
    source_api_url           TEXT NOT NULL,
    target_api_url           TEXT NOT NULL,
    method                   VARCHAR(10) DEFAULT 'POST',
    is_active                BOOLEAN DEFAULT true,
    created_at               TIMESTAMP DEFAULT now(),
    updated_at               TIMESTAMP DEFAULT now(),
    protocol                 VARCHAR(10) DEFAULT 'HTTP',
    sftp_host                TEXT,
    sftp_port                INTEGER DEFAULT 22,
    sftp_username            TEXT,
    sftp_password            TEXT,
    sftp_private_key_path    TEXT,
    sftp_remote_path         TEXT,
    dynamic_filename_pattern VARCHAR(255),
    api_id                   TEXT,
    api_password             TEXT,
    api_auth_url             TEXT,
    request_content_type     VARCHAR(20) DEFAULT 'JSON',
    require_authentication   BOOLEAN DEFAULT false,
    require_correlation_id   BOOLEAN DEFAULT true,
    description              TEXT,
    mock_response            JSONB,
    mock_enabled             BOOLEAN DEFAULT false,
    tenant_id                VARCHAR(255),
    rate_limit_rpm           INTEGER DEFAULT 60,
    is_hidden                BOOLEAN DEFAULT false,
    created_by               INTEGER,
    updated_by               INTEGER
);

-- Route lookups: resolve an active endpoint by target URL + method.
CREATE INDEX IF NOT EXISTS idx_api_endpoints_routing
    ON api_endpoints (target_api_url, method, is_active);

-- ----------------------------------------------------------------------------
-- parameter_mappings — source -> target parameter transformations per endpoint.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS parameter_mappings (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    api_endpoint_id  UUID NOT NULL REFERENCES api_endpoints (id) ON DELETE CASCADE,
    source_parameter VARCHAR(255) NOT NULL,
    target_parameter VARCHAR(255) NOT NULL,
    data_type        VARCHAR(20) DEFAULT 'STRING',
    parameter_type   VARCHAR(20) DEFAULT 'BODY',
    is_active        BOOLEAN DEFAULT true,
    created_at       TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_parameter_mappings_lookup
    ON parameter_mappings (api_endpoint_id, is_active);

-- ----------------------------------------------------------------------------
-- api_call_logs — full audit trail of proxied calls. endpoint_id becomes NULL
-- (instead of deleting history) when an endpoint is removed.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS api_call_logs (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    endpoint_id                 UUID REFERENCES api_endpoints (id) ON DELETE SET NULL,
    request_id                  UUID NOT NULL,
    method                      VARCHAR(10) NOT NULL,
    path                        TEXT NOT NULL,
    status                      VARCHAR(20) NOT NULL,
    overall_status              BOOLEAN DEFAULT false,
    internal_request_headers    JSONB DEFAULT '{}',
    internal_request_body       JSONB DEFAULT '{}',
    internal_api_client_response JSONB DEFAULT '{}',
    internal_api_client_status  VARCHAR(20),
    external_request_url        TEXT,
    external_request_method     VARCHAR(10),
    external_request_headers    JSONB DEFAULT '{}',
    external_request_body       JSONB DEFAULT '{}',
    external_query_params       JSONB DEFAULT '{}',
    external_response           JSONB,
    external_response_headers   JSONB DEFAULT '{}',
    external_response_time_ms   INTEGER DEFAULT 0,
    external_status_code        INTEGER,
    total_time_ms               INTEGER DEFAULT 0,
    full_log                    TEXT,
    timeout_configured          INTEGER DEFAULT 60,
    tenant_id                   VARCHAR(255),
    created_at                  TIMESTAMP DEFAULT now()
);

-- Log listing: newest entries per endpoint.
CREATE INDEX IF NOT EXISTS idx_api_call_logs_recent
    ON api_call_logs (endpoint_id, created_at DESC);

-- ----------------------------------------------------------------------------
-- users / roles / user_roles — authentication and authorization.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    user_name     VARCHAR(50) NOT NULL,
    email         VARCHAR(100) UNIQUE,
    password_hash VARCHAR(1000) NOT NULL,
    is_active     BOOLEAN DEFAULT true,
    created_at    TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS roles (
    id        SERIAL PRIMARY KEY,
    role_name VARCHAR(50) UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS user_roles (
    id      SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    role_id INTEGER NOT NULL REFERENCES roles (id) ON DELETE CASCADE,
    UNIQUE (user_id, role_id)
);

-- ----------------------------------------------------------------------------
-- updated_at maintenance for api_endpoints
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_api_endpoints_updated_at ON api_endpoints;
CREATE TRIGGER trg_api_endpoints_updated_at
    BEFORE UPDATE ON api_endpoints
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();

-- ----------------------------------------------------------------------------
-- Seed data
-- ----------------------------------------------------------------------------

-- Default roles.
INSERT INTO roles (role_name)
VALUES ('admin'), ('user'), ('viewer')
ON CONFLICT (role_name) DO NOTHING;

-- Default administrator — email admin@mapper.com, password admin123.
-- Hash generated with passlib argon2id (m=65536, t=3, p=4).
INSERT INTO users (user_name, email, password_hash, is_active)
VALUES (
    'admin',
    'admin@mapper.com',
    '$argon2id$v=19$m=65536,t=3,p=4$htDae69VCkEIwdj7P0fIeQ$rekf0foHR0aZspGRDFs9O6eylbfsrUI3kg3zCkD5xOg',
    true
)
ON CONFLICT (email) DO NOTHING;

-- Grant the admin role to the default administrator.
INSERT INTO user_roles (user_id, role_id)
SELECT u.id, r.id
FROM users u
CROSS JOIN roles r
WHERE u.email = 'admin@mapper.com'
  AND r.role_name = 'admin'
ON CONFLICT (user_id, role_id) DO NOTHING;
