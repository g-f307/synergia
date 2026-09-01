CREATE TABLE synergia.identity_login_attempts (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    identifier_hash text NOT NULL CHECK (identifier_hash ~ '^[0-9a-f]{64}$'),
    ip_hash text CHECK (ip_hash IS NULL OR ip_hash ~ '^[0-9a-f]{64}$'),
    succeeded boolean NOT NULL DEFAULT false,
    attempted_at timestamptz NOT NULL DEFAULT now(),
    blocked_until timestamptz,
    CHECK (blocked_until IS NULL OR blocked_until >= attempted_at)
);

CREATE INDEX idx_identity_login_attempts_window
    ON synergia.identity_login_attempts (identifier_hash, attempted_at DESC)
    WHERE succeeded = false;

COMMENT ON TABLE synergia.identity_login_attempts IS
    'Janela operacional de limitacao; identificadores e IPs sao protegidos por HMAC';
