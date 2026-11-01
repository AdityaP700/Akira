import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text

from app.api.routers import (
    audit,
    balances,
    dev,
    expenses,
    groups,
    health,
    notifications,
    settlements,
    users,
    webhooks,
)
from app.core.config import settings
from app.core.db import engine
from app.core.errors import register_error_handlers
from app.core.logging import RequestLoggingMiddleware, setup_logging
from app.security.demo_gate import DemoGateMiddleware
from app.security.edge import EdgeHardeningMiddleware, SecurityHeadersMiddleware
from app.security.ratelimit import limiter

startup_logger = logging.getLogger("app.startup")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager that logs database connection role once at startup."""
    try:
        with engine.connect() as conn:
            current_user = conn.execute(text("SELECT current_user")).scalar()
            startup_logger.info(
                "Database connected as %s",
                current_user,
                extra={"event": "db_connected", "db_user": current_user},
            )
    except Exception as exc:
        startup_logger.warning("Could not verify DB user on startup: %s", exc)
    yield


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    setup_logging()

    # Disable interactive documentation in production (GUARDRAILS P9 / OWASP API9)
    docs_url = "/docs" if settings.APP_ENV != "prod" else None
    redoc_url = "/redoc" if settings.APP_ENV != "prod" else None
    openapi_url = "/openapi.json" if settings.APP_ENV != "prod" else None

    app = FastAPI(
        title="Akira Expense Sharing Service",
        description="Backend service for groups to record shared expenses and settle balances",
        version="0.1.0",
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
        lifespan=lifespan,
    )

    # Attach slowapi rate limiter state
    app.state.limiter = limiter

    # Middleware stack:
    # 1. RequestLoggingMiddleware (outermost: logs request_id, latency ms, status, actor)
    # 2. EdgeHardeningMiddleware (64 KB body size limit -> 413, JSON content type -> 415)
    # 3. DemoGateMiddleware (gates all demo routes with DEMO_ACCESS_KEY -> 401, health exempt)
    # 4. SlowAPIMiddleware (rate limiting enforcement -> 429)
    # 5. SecurityHeadersMiddleware (injects defensive security headers on all responses)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(DemoGateMiddleware)
    app.add_middleware(EdgeHardeningMiddleware)
    app.add_middleware(RequestLoggingMiddleware)

    # Global security scheme configuration for OpenAPI / Swagger UI
    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        components = openapi_schema.setdefault("components", {})
        security_schemes = components.setdefault("securitySchemes", {})
        security_schemes["DemoKeyAuth"] = {
            "type": "apiKey",
            "in": "header",
            "name": "X-Demo-Key",
            "description": (
                "Demo deployment access key required for all routes "
                "when APP_ENV=demo (except GET /health)."
            ),
        }
        global_security = openapi_schema.setdefault("security", [])
        if {"DemoKeyAuth": []} not in global_security:
            global_security.append({"DemoKeyAuth": []})
        app.openapi_schema = openapi_schema
        return app.openapi_schema

    app.openapi = custom_openapi

    # Global error handlers
    register_error_handlers(app)

    # Include core routers
    app.include_router(health.router)
    app.include_router(users.router)
    app.include_router(groups.router)
    app.include_router(expenses.router)
    app.include_router(balances.router)
    app.include_router(settlements.router)
    app.include_router(notifications.router)
    app.include_router(audit.router)
    app.include_router(webhooks.router)

    # Include mock-provider dev simulation routes only in non-production environments
    if settings.APP_ENV != "prod":
        app.include_router(dev.router)

    return app


app = create_app()
