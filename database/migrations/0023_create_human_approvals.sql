UPDATE synergia.permission_catalog_versions SET is_active = false WHERE is_active;

INSERT INTO synergia.permission_catalog_versions (version, description, is_active)
VALUES ('1.3.0', 'Permissões de decisão humana auditável', true);

INSERT INTO synergia.permissions (
    permission_key, resource_type, description, catalog_version, is_reserved
) VALUES
    ('approval.read', 'approval', 'Consultar solicitações e histórico de decisão', '1.3.0', true),
    ('approval.submit', 'approval', 'Submeter pendência para decisão humana', '1.3.0', true),
    ('approval.assign', 'approval', 'Atribuir solicitação para análise', '1.3.0', true),
    ('approval.decide', 'approval', 'Aprovar, rejeitar ou devolver solicitação', '1.3.0', true)
ON CONFLICT (normalized_key) DO NOTHING;

INSERT INTO synergia.role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM synergia.roles r
JOIN synergia.permissions p ON (
    (r.normalized_key = 'gestor' AND p.normalized_key IN (
        'approval.read', 'approval.submit', 'approval.assign', 'approval.decide'
    )) OR
    (r.normalized_key IN ('analista', 'operador') AND p.normalized_key IN (
        'approval.read', 'approval.submit'
    ))
)
ON CONFLICT (role_id, permission_id) WHERE revoked_at IS NULL DO NOTHING;

ALTER TABLE synergia.notification_template_versions
    DROP CONSTRAINT notification_template_versions_resource_type_check;
ALTER TABLE synergia.notification_template_versions
    ADD CONSTRAINT notification_template_versions_resource_type_check
    CHECK (resource_type IN ('execution', 'pending', 'report', 'approval'));
ALTER TABLE synergia.notifications
    DROP CONSTRAINT notifications_resource_type_check;
ALTER TABLE synergia.notifications
    ADD CONSTRAINT notifications_resource_type_check
    CHECK (resource_type IN ('execution', 'pending', 'report', 'approval'));

INSERT INTO synergia.notification_template_versions (
    notification_type, template_version, required_permission, resource_type
) VALUES
    ('approval.submitted', '1.0.0', 'approval.read', 'approval'),
    ('approval.assigned', '1.0.0', 'approval.read', 'approval'),
    ('approval.approved', '1.0.0', 'approval.read', 'approval'),
    ('approval.rejected', '1.0.0', 'approval.read', 'approval'),
    ('approval.returned', '1.0.0', 'approval.read', 'approval'),
    ('approval.resubmitted', '1.0.0', 'approval.read', 'approval');

INSERT INTO synergia.notification_templates (
    notification_type, template_version, locale, title_template, body_template
) VALUES
    ('approval.submitted', '1.0.0', 'pt-BR', 'Solicitação enviada', 'A pendência {pending_id} aguarda análise.'),
    ('approval.submitted', '1.0.0', 'en-US', 'Request submitted', 'Pending item {pending_id} is awaiting review.'),
    ('approval.assigned', '1.0.0', 'pt-BR', 'Análise atribuída', 'A pendência {pending_id} foi atribuída para análise.'),
    ('approval.assigned', '1.0.0', 'en-US', 'Review assigned', 'Pending item {pending_id} was assigned for review.'),
    ('approval.approved', '1.0.0', 'pt-BR', 'Solicitação aprovada', 'A pendência {pending_id} foi aprovada.'),
    ('approval.approved', '1.0.0', 'en-US', 'Request approved', 'Pending item {pending_id} was approved.'),
    ('approval.rejected', '1.0.0', 'pt-BR', 'Solicitação rejeitada', 'A pendência {pending_id} foi rejeitada.'),
    ('approval.rejected', '1.0.0', 'en-US', 'Request rejected', 'Pending item {pending_id} was rejected.'),
    ('approval.returned', '1.0.0', 'pt-BR', 'Correção solicitada', 'A pendência {pending_id} foi devolvida para correção.'),
    ('approval.returned', '1.0.0', 'en-US', 'Correction requested', 'Pending item {pending_id} was returned for correction.'),
    ('approval.resubmitted', '1.0.0', 'pt-BR', 'Solicitação reenviada', 'A pendência {pending_id} aguarda nova análise.'),
    ('approval.resubmitted', '1.0.0', 'en-US', 'Request resubmitted', 'Pending item {pending_id} is awaiting another review.');

CREATE TABLE synergia.approval_policies (
    policy_key text NOT NULL,
    version integer NOT NULL CHECK (version > 0),
    review_group text NOT NULL CHECK (btrim(review_group) <> ''),
    require_distinct_approver boolean NOT NULL DEFAULT true,
    require_approval_justification boolean NOT NULL DEFAULT true,
    require_rejection_justification boolean NOT NULL DEFAULT true,
    require_return_justification boolean NOT NULL DEFAULT true,
    is_active boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (policy_key, version)
);

CREATE UNIQUE INDEX uq_approval_policy_active
    ON synergia.approval_policies (policy_key) WHERE is_active;

INSERT INTO synergia.approval_policies (
    policy_key, version, review_group, require_distinct_approver,
    require_approval_justification, require_rejection_justification,
    require_return_justification, is_active
) VALUES ('pending.standard', 1, 'gestor', true, true, true, true, true);

CREATE FUNCTION synergia.prevent_published_approval_policy_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'published_approval_policy_is_immutable' USING ERRCODE = '55000';
END;
$$;

CREATE TRIGGER approval_policies_published_immutable
BEFORE UPDATE OR DELETE ON synergia.approval_policies
FOR EACH ROW WHEN (OLD.is_active)
EXECUTE FUNCTION synergia.prevent_published_approval_policy_mutation();

CREATE TABLE synergia.approval_requests (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    pending_item_id bigint NOT NULL REFERENCES synergia.pending_items(id),
    organization_id uuid NOT NULL REFERENCES synergia.iam_organizations(id),
    requester_user_id uuid NOT NULL REFERENCES synergia.identity_users(id),
    requester_session_id uuid NOT NULL REFERENCES synergia.identity_sessions(id),
    assignee_user_id uuid REFERENCES synergia.identity_users(id),
    review_group text NOT NULL CHECK (btrim(review_group) <> ''),
    policy_key text NOT NULL,
    policy_version integer NOT NULL,
    state text NOT NULL CHECK (state IN (
        'draft', 'submitted', 'in_review', 'approved', 'rejected', 'returned'
    )),
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    submitted_at timestamptz,
    decided_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (policy_key, policy_version)
        REFERENCES synergia.approval_policies(policy_key, version)
);

CREATE UNIQUE INDEX uq_approval_request_active_pending
    ON synergia.approval_requests (pending_item_id)
    WHERE state IN ('draft', 'submitted', 'in_review', 'returned');
CREATE INDEX idx_approval_requests_org_state
    ON synergia.approval_requests (organization_id, state, updated_at DESC, id);

CREATE TABLE synergia.approval_stages (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id uuid NOT NULL REFERENCES synergia.approval_requests(id),
    sequence integer NOT NULL CHECK (sequence > 0),
    review_group text NOT NULL CHECK (btrim(review_group) <> ''),
    assignee_user_id uuid REFERENCES synergia.identity_users(id),
    state text NOT NULL CHECK (state IN ('waiting', 'in_review', 'completed', 'returned')),
    opened_at timestamptz NOT NULL DEFAULT now(),
    closed_at timestamptz,
    UNIQUE (request_id, sequence)
);

CREATE TABLE synergia.approval_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id uuid NOT NULL REFERENCES synergia.approval_requests(id),
    event_type text NOT NULL CHECK (event_type IN (
        'created', 'submitted', 'assigned', 'reassigned',
        'approved', 'rejected', 'returned', 'resubmitted'
    )),
    from_state text,
    to_state text NOT NULL,
    actor_user_id uuid NOT NULL REFERENCES synergia.identity_users(id),
    actor_session_id uuid NOT NULL REFERENCES synergia.identity_sessions(id),
    organization_id uuid NOT NULL REFERENCES synergia.iam_organizations(id),
    actor_permissions jsonb NOT NULL DEFAULT '[]'::jsonb,
    assignee_user_id uuid REFERENCES synergia.identity_users(id),
    justification text,
    consent boolean NOT NULL DEFAULT false,
    request_version integer NOT NULL CHECK (request_version > 0),
    correlation_id uuid NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    CHECK (justification IS NULL OR btrim(justification) <> '')
);

CREATE INDEX idx_approval_events_request
    ON synergia.approval_events (request_id, occurred_at, id);

CREATE FUNCTION synergia.prevent_approval_event_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'approval events are append-only'
        USING ERRCODE = 'object_not_in_prerequisite_state';
END;
$$;

CREATE TRIGGER trg_approval_events_immutable
BEFORE UPDATE OR DELETE ON synergia.approval_events
FOR EACH ROW EXECUTE FUNCTION synergia.prevent_approval_event_mutation();
