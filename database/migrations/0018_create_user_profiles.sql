ALTER TABLE synergia.identity_users
    ADD COLUMN locale text NOT NULL DEFAULT 'pt-BR',
    ADD COLUMN timezone text NOT NULL DEFAULT 'America/Manaus',
    ADD COLUMN notification_preferences jsonb NOT NULL DEFAULT
        '{"email":true,"in_app":true}'::jsonb,
    ADD COLUMN avatar_storage_key text,
    ADD COLUMN avatar_media_type text,
    ADD COLUMN avatar_size_bytes bigint,
    ADD COLUMN avatar_sha256 text,
    ADD COLUMN avatar_updated_at timestamptz,
    ADD CONSTRAINT ck_identity_users_locale
        CHECK (locale IN ('pt-BR', 'en-US', 'es-ES')),
    ADD CONSTRAINT ck_identity_users_timezone
        CHECK (btrim(timezone) <> ''),
    ADD CONSTRAINT ck_identity_users_notification_preferences
        CHECK (jsonb_typeof(notification_preferences) = 'object'),
    ADD CONSTRAINT ck_identity_users_avatar_metadata
        CHECK (
            (avatar_storage_key IS NULL AND avatar_media_type IS NULL
                AND avatar_size_bytes IS NULL AND avatar_sha256 IS NULL
                AND avatar_updated_at IS NULL)
            OR
            (avatar_storage_key IS NOT NULL
                AND avatar_media_type IN ('image/png', 'image/jpeg', 'image/webp')
                AND avatar_size_bytes > 0
                AND avatar_sha256 ~ '^[0-9a-f]{64}$'
                AND avatar_updated_at IS NOT NULL)
        );

CREATE UNIQUE INDEX uq_identity_users_avatar_storage_key
    ON synergia.identity_users (avatar_storage_key)
    WHERE avatar_storage_key IS NOT NULL;

COMMENT ON COLUMN synergia.identity_users.notification_preferences IS
    'Preferencias pessoais; nao representa consentimento para envio externo';

COMMENT ON COLUMN synergia.identity_users.avatar_storage_key IS
    'Identificador interno aleatorio; nunca deriva do nome enviado pelo cliente';
