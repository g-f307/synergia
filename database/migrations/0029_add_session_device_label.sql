ALTER TABLE synergia.identity_sessions
    ADD COLUMN device_label text NOT NULL DEFAULT 'Dispositivo desconhecido'
    CHECK (char_length(device_label) BETWEEN 1 AND 80);

COMMENT ON COLUMN synergia.identity_sessions.device_label IS
    'Rotulo generico de navegador e sistema; User-Agent bruto nao e armazenado';
