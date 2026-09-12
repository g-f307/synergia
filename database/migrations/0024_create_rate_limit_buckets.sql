CREATE TABLE synergia.rate_limit_buckets (
    operation text NOT NULL,
    dimension text NOT NULL,
    key_hash text NOT NULL CHECK (key_hash ~ '^[0-9a-f]{64}$'),
    window_started_at timestamptz NOT NULL,
    window_expires_at timestamptz NOT NULL,
    request_count integer NOT NULL CHECK (request_count >= 0),
    denied_count integer NOT NULL DEFAULT 0 CHECK (denied_count >= 0),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (operation, dimension, key_hash),
    CHECK (window_expires_at > window_started_at)
);

CREATE TABLE synergia.rate_limit_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    operation text NOT NULL,
    dimension text NOT NULL,
    key_hash text NOT NULL CHECK (key_hash ~ '^[0-9a-f]{64}$'),
    retry_after_seconds integer NOT NULL CHECK (retry_after_seconds > 0),
    correlation_id uuid,
    method text NOT NULL,
    route_group text NOT NULL
);

CREATE INDEX idx_rate_limit_events_operation_time
    ON synergia.rate_limit_events (operation, occurred_at DESC);
CREATE INDEX idx_rate_limit_events_retention
    ON synergia.rate_limit_events (occurred_at);
CREATE INDEX idx_rate_limit_buckets_updated_at
    ON synergia.rate_limit_buckets (updated_at);

COMMENT ON TABLE synergia.rate_limit_buckets IS
    'Contadores compartilhados de abuso; chaves protegidas por HMAC e sem payload';
COMMENT ON TABLE synergia.rate_limit_events IS
    'Negacoes observaveis sem credenciais, IPs, parametros ou conteudo sensivel';
