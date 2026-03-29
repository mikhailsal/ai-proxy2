"""FastAPI application factory."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ai_proxy.adapters.registry import build_registry
from ai_proxy.api.proxy.router import router as proxy_router
from ai_proxy.api.ui.chats import router as chats_router
from ai_proxy.api.ui.export import router as export_router
from ai_proxy.api.ui.requests import router as requests_router
from ai_proxy.config.loader import load_config
from ai_proxy.config.settings import get_settings
from ai_proxy.db.engine import dispose_engine, init_engine
from ai_proxy.logging.service import start_logging_service, stop_logging_service

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
    settings = get_settings()

    # Init database
    init_engine(settings.database_url)
    logger.info("database_initialized")

    # Create tables if needed
    from ai_proxy.db.engine import get_engine
    from ai_proxy.db.models import Base
    engine = get_engine()
    if engine:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("database_tables_created")

    # Load config
    config = load_config(settings.config_path)

    # Build adapter registry
    build_registry(config)

    # Start logging service
    log_cfg = config.logging
    start_logging_service(
        batch_size=log_cfg.batch_size,
        flush_interval=log_cfg.flush_interval_seconds,
    )
    logger.info("logging_service_started")

    yield

    # Shutdown
    await stop_logging_service()
    await dispose_engine()
    logger.info("shutdown_complete")


def create_app() -> FastAPI:
    """Application factory."""
    application = FastAPI(
        title="AI Proxy v2",
        description="Transparent proxy for AI model providers with logging and visualization",
        version="2.0.0",
        lifespan=lifespan,
    )

    settings = get_settings()

    # CORS
    origins = [o.strip() for o in settings.cors_origins.split(",")]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health endpoint
    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    # Admin endpoint
    @application.post("/admin/reload-config")
    async def reload_config() -> dict[str, str]:
        from ai_proxy.config.loader import reload_config as do_reload
        settings = get_settings()
        config = do_reload(settings.config_path)
        build_registry(config)
        return {"status": "reloaded"}

    # Include routers
    application.include_router(proxy_router)
    application.include_router(requests_router)
    application.include_router(chats_router)
    application.include_router(export_router)

    return application


app = create_app()
