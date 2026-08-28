from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.errors import install_error_handlers
from app.imports import router as imports_router
from app.queries import router as queries_router

app = FastAPI(
    title="SYNERGIA API",
    version="0.2.0",
    description=(
        "Contratos estáveis para importação, acompanhamento, consultas, "
        "pendências e reprocessamento do SYNERGIA."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

install_error_handlers(app)
app.include_router(imports_router)
app.include_router(queries_router)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "synergia-api"}
