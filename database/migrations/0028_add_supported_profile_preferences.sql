ALTER TABLE synergia.identity_users
    ADD COLUMN ui_density text NOT NULL DEFAULT 'comfortable',
    ADD COLUMN font_scale text NOT NULL DEFAULT 'normal',
    ADD CONSTRAINT ck_identity_users_ui_density
        CHECK (ui_density IN ('comfortable', 'compact')),
    ADD CONSTRAINT ck_identity_users_font_scale
        CHECK (font_scale IN ('small', 'normal', 'large'));

COMMENT ON COLUMN synergia.identity_users.ui_density IS
    'Preferência pessoal de densidade da interface, aplicada no shell Angular.';
COMMENT ON COLUMN synergia.identity_users.font_scale IS
    'Preferência pessoal de escala tipográfica, aplicada no shell Angular.';
