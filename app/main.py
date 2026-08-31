"""FastAPI app factory and route registration."""
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routes_chat import router as chat_router
from app.api.routes_debug_auth import router as debug_auth_router
from app.api.routes_health import router as health_router
from app.api.routes_metrics import router as metrics_router
from app.api.routes_stats import router as stats_router


def create_app() -> FastAPI:
    app = FastAPI(title="LLM Gateway")
    app.include_router(health_router)
    app.include_router(debug_auth_router)
    app.include_router(chat_router)
    app.include_router(metrics_router)
    app.include_router(stats_router)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        # PLAN.md Section 5 specifies 400 (not FastAPI's default 422) for
        # malformed /v1/chat request bodies (missing messages, invalid role,
        # empty content, etc.).
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_request", "message": jsonable_encoder(exc.errors())},
        )

    return app


app = create_app()
