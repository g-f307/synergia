from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.imports import router as imports_router

app = FastAPI(title="SYNERGIA API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(imports_router)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "synergia-api"}
