ALTER TABLE synergia.identity_users
    ADD COLUMN version integer NOT NULL DEFAULT 1 CHECK (version > 0);

CREATE OR REPLACE FUNCTION synergia.touch_identity_user()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = now();
    NEW.version = OLD.version + 1;
    RETURN NEW;
END;
$$;

COMMENT ON COLUMN synergia.identity_users.version IS
    'Versao otimista incrementada em toda alteracao do usuario';
