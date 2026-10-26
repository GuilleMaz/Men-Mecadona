"""Punto de entrada de la API de Cesta."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session, sessionmaker

from app.api import catalog, health
from app.api.errors import (
    ApiError,
    api_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.config import APP_NAME, APP_VERSION, Settings, get_settings
from app.db import get_session, get_session_factory
from app.security import HostValidationMiddleware
from app.services.catalog_sync import CatalogSyncService

API_PREFIX = "/api"

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    session_factory: sessionmaker[Session] | None = None,
) -> FastAPI:
    """Construye la aplicación FastAPI.

    CORS solo se activa en desarrollo y solo para el origen del servidor de Vite.
    Todas las peticiones pasan por la validación de `Host` local. La sync de
    arranque se lanza en segundo plano y nunca bloquea el startup.
    """
    resolved = settings or get_settings()
    factory = session_factory or get_session_factory()
    sync_service = CatalogSyncService(factory)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        del application
        try:
            sync_service.recover_interrupted_runs()
        except Exception:  # noqa: BLE001 - una base sin migrar no debe impedir arrancar
            logger.warning("No se pudieron recuperar syncs interrumpidas", exc_info=True)

        if resolved.sync_on_startup and resolved.app_env != "test":
            try:
                sync_service.start_if_due()
            except Exception:  # noqa: BLE001 - arrancar sin red sigue siendo válido
                logger.warning("No se pudo lanzar la sync de arranque", exc_info=True)

        yield

        await sync_service.shutdown()

    application = FastAPI(
        title=APP_NAME,
        version=APP_VERSION,
        description=(
            "API local para generar menús de comida y cena para N personas, N días "
            "y un presupuesto, con precios de la tienda online de Mercadona."
        ),
        lifespan=lifespan,
    )
    application.state.catalog_sync = sync_service
    application.state.session_factory = factory

    if session_factory is not None:

        def _session_override() -> Iterator[Session]:
            with session_factory() as session:
                yield session

        application.dependency_overrides[get_session] = _session_override

    application.add_exception_handler(ApiError, api_exception_handler)
    application.add_exception_handler(RequestValidationError, validation_exception_handler)
    application.add_exception_handler(HTTPException, http_exception_handler)

    cors_origins = resolved.cors_origins
    if cors_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["*"],
        )

    # Se añade después de CORS para que la validación de Host sea la capa más externa.
    application.add_middleware(
        HostValidationMiddleware,
        allowed_hosts=resolved.allowed_hosts,
    )

    application.include_router(health.router, prefix=API_PREFIX)
    application.include_router(catalog.router, prefix=API_PREFIX)
    return application


app = create_app()
