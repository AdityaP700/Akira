from fastapi import FastAPI

from app.api.routers import balances, expenses, groups, health, settlements, users
from app.core.config import settings
from app.core.errors import register_error_handlers
from app.core.logging import RequestIDMiddleware, setup_logging


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    setup_logging()

    # Disable interactive documentation in production (GUARDRAILS P9)
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
    )

    # Middleware
    app.add_middleware(RequestIDMiddleware)

    # Global error handlers
    register_error_handlers(app)

    # Include routers
    app.include_router(health.router)
    app.include_router(users.router)
    app.include_router(groups.router)
    app.include_router(expenses.router)
    app.include_router(balances.router)
    app.include_router(settlements.router)

    return app


app = create_app()
