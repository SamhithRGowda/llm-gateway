"""FastAPI app factory and route registration."""
from fastapi import FastAPI

from app.api.routes_debug_auth import router as debug_auth_router
from app.api.routes_health import router as health_router


def create_app() -> FastAPI:
    app = FastAPI(title="LLM Gateway")
    app.include_router(health_router)
    app.include_router(debug_auth_router)
    return app


app = create_app()
