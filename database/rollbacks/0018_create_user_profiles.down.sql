DROP INDEX IF EXISTS synergia.uq_identity_users_avatar_storage_key;

ALTER TABLE synergia.identity_users
    DROP CONSTRAINT IF EXISTS ck_identity_users_avatar_metadata,
    DROP CONSTRAINT IF EXISTS ck_identity_users_notification_preferences,
    DROP CONSTRAINT IF EXISTS ck_identity_users_timezone,
    DROP CONSTRAINT IF EXISTS ck_identity_users_locale,
    DROP COLUMN IF EXISTS avatar_updated_at,
    DROP COLUMN IF EXISTS avatar_sha256,
    DROP COLUMN IF EXISTS avatar_size_bytes,
    DROP COLUMN IF EXISTS avatar_media_type,
    DROP COLUMN IF EXISTS avatar_storage_key,
    DROP COLUMN IF EXISTS notification_preferences,
    DROP COLUMN IF EXISTS timezone,
    DROP COLUMN IF EXISTS locale;
