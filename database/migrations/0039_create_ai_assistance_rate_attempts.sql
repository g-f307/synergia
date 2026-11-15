CREATE TABLE synergia.ai_assistance_rate_attempts (
    dimension text NOT NULL CHECK (dimension IN ('user', 'organization')),
    key_hash text NOT NULL CHECK (key_hash ~ '^[0-9a-f]{64}$'),
    occurred_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX ai_assistance_rate_attempts_lookup
    ON synergia.ai_assistance_rate_attempts (dimension, key_hash, occurred_at);
CREATE INDEX ai_assistance_rate_attempts_expiry
    ON synergia.ai_assistance_rate_attempts (occurred_at);
