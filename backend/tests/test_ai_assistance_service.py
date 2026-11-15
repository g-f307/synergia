from uuid import uuid4

import pytest
from test_ai_assistance_generator import Fake, context

from app.ai_assistance_generator import AiAssistanceGenerator
from app.ai_assistance_provider import ProviderError
from app.ai_assistance_repository import AssistancePersistenceError
from app.ai_assistance_service import AiAssistanceService
from app.authorization import ActorContext
from app.errors import ApiError


class Contexts:
    def __init__(self, value):
        self.value = value

    def organization(self, actor, execution_id):
        organization = self.value.subject.organization_id
        return organization if actor.allows("execution.read", organization) else None

    def build(self, actor, execution_id):
        if not actor.allows("execution.read", self.value.subject.organization_id):
            raise ApiError(404, "resource_not_found", "Recurso nao encontrado")
        return self.value


class Repository:
    def __init__(self):
        self.result = None
        self.reservations = 0
        self.conflict = False

    def find(self, *args, **kwargs):
        return self.result

    def latest(self, *args, **kwargs):
        return self.result

    def reserve(self, *args):
        if self.conflict:
            raise AssistancePersistenceError("conflict_or_not_found")
        self.reservations += 1
        return uuid4()

    def finish(self, key, assistance_id, actor, correlation, response, **kwargs):
        self.result = response
        return response

    def abandon(self, *args):
        pass


def make_actor(ctx, *actions):
    org = ctx.subject.organization_id
    return ActorContext(
        uuid4(),
        uuid4(),
        uuid4(),
        {key: frozenset({org}) for key in ("execution.read", *actions)},
        uuid4(),
    )


def test_insufficient_is_persisted_and_reused_without_provider():
    ctx = context("insufficient")
    provider = Fake(b"never")
    repo = Repository()
    service = AiAssistanceService(Contexts(ctx), AiAssistanceGenerator(provider), repo)
    actor = make_actor(ctx, "ai.assistance.generate", "ai.assistance.read")
    first = service.generate(actor, ctx.subject.execution_id)
    second = service.generate(actor, ctx.subject.execution_id)
    assert first == second == service.latest(actor, ctx.subject.execution_id)
    assert first.state == "insufficient_evidence"
    assert provider.calls == 0 and repo.reservations == 1


def test_rejected_output_is_persisted():
    ctx = context()
    provider = Fake(b"invalid json")
    repo = Repository()
    service = AiAssistanceService(Contexts(ctx), AiAssistanceGenerator(provider), repo)
    result = service.generate(
        make_actor(ctx, "ai.assistance.generate"), ctx.subject.execution_id
    )
    assert result.state == "rejected" and repo.result == result
    assert provider.calls == 1


@pytest.mark.parametrize(
    "code,status",
    [("runtime_timeout", 504), ("runtime_unavailable", 503), ("runtime_busy", 409)],
)
def test_runtime_errors_are_stable(code, status):
    ctx = context()
    service = AiAssistanceService(
        Contexts(ctx), AiAssistanceGenerator(Fake(ProviderError(code))), Repository()
    )
    with pytest.raises(ApiError) as exc:
        service.generate(
            make_actor(ctx, "ai.assistance.generate"), ctx.subject.execution_id
        )
    assert exc.value.status_code == status


def test_scope_intersection_and_conflict():
    ctx = context()
    repo = Repository()
    service = AiAssistanceService(
        Contexts(ctx), AiAssistanceGenerator(Fake(b"never")), repo
    )
    actor = make_actor(ctx, "ai.assistance.generate")
    actor.permissions["ai.assistance.generate"] = frozenset({uuid4()})
    with pytest.raises(ApiError) as exc:
        service.generate(actor, ctx.subject.execution_id)
    assert exc.value.status_code == 404
    actor = make_actor(ctx, "ai.assistance.generate")
    repo.conflict = True
    with pytest.raises(ApiError) as exc:
        service.generate(actor, ctx.subject.execution_id)
    assert (exc.value.status_code, exc.value.code) == (409, "ai_assistance_in_progress")


def test_latest_does_not_call_generator_and_requires_read_permission():
    ctx = context()
    provider = Fake(b"never")
    repo = Repository()
    service = AiAssistanceService(Contexts(ctx), AiAssistanceGenerator(provider), repo)
    with pytest.raises(ApiError) as exc:
        service.latest(
            make_actor(ctx, "ai.assistance.generate"), ctx.subject.execution_id
        )
    assert exc.value.status_code == 403
    with pytest.raises(ApiError) as exc:
        service.latest(make_actor(ctx, "ai.assistance.read"), ctx.subject.execution_id)
    assert (exc.value.status_code, exc.value.code) == (404, "ai_assistance_not_found")
    assert provider.calls == 0


def test_integrity_failure_is_sanitized():
    class Corrupt(Repository):
        def latest(self, *args, **kwargs):
            raise AssistancePersistenceError("integrity_error")

    ctx = context()
    service = AiAssistanceService(
        Contexts(ctx), AiAssistanceGenerator(Fake(b"")), Corrupt()
    )
    with pytest.raises(ApiError) as exc:
        service.latest(make_actor(ctx, "ai.assistance.read"), ctx.subject.execution_id)
    assert (exc.value.status_code, exc.value.code) == (
        500,
        "ai_assistance_integrity_error",
    )
