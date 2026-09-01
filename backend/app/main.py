from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.access_control import router as access_control_router
from app.auth.config import configured_allowed_origins
from app.auth.routes import router as auth_router
from app.errors import install_error_handlers
from app.execution_monitoring import router as monitoring_router
from app.imports import router as imports_router
from app.profile import router as profile_router
from app.queries import router as queries_router
from app.request_context import CorrelationIdMiddleware
from app.users import router as users_router


def create_app() -> FastAPI:
    application = FastAPI(
        title="SYNERGIA API",
        version="0.5.0",
        description=(
            "Contratos estáveis para importação, acompanhamento, consultas, "
            "pendências, reprocessamento, identidade e perfil do SYNERGIA."
        ),
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(configured_allowed_origins()),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_middleware(CorrelationIdMiddleware)
    install_error_handlers(application)
    application.include_router(auth_router)
    application.include_router(imports_router)
    application.include_router(queries_router)
    application.include_router(monitoring_router)
    application.include_router(users_router)
    application.include_router(access_control_router)
    application.include_router(profile_router)

    @application.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "synergia-api"}

    return application


app = create_app()
