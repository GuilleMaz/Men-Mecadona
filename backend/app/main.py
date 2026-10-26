"""Punto de entrada de la API de Cesta."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session, sessionmaker

from app.api import catalog, domain, health
from app.api.errors import (
    ApiError,
    api_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.config import APP_NAME, APP_VERSION, Settings, get_settings
from app.db import get_session, get_session_factory
from app.security import HostValidationMiddleware
from app.services.allergen_sync import AllergenSyncService
from app.services.catalog_sync import CatalogSyncService
from app.services.seed import SeedService

API_PREFIX = "/api"

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    session_factory: sessionmaker[Session] | None = None,
) -> FastAPI:
    """Construye la aplicación FastAPI.

    CORS solo se activa en desarrollo y solo para el origen del servidor de Vite.
    Todas las peticiones pasan por la validación de `Host` local. La sync de
    arranque y la carga del seed se lanzan en segundo plano y nunca bloquean el
    startup.
    """
    resolved = settings or get_settings()
    factory = session_factory or get_session_factory()
    seed_service = SeedService(factory)
    allergen_service = AllergenSyncService(factory)

    warm_lock = asyncio.Lock()

    async def warm_data() -> None:
        """Carga el seed y enriquece alérgenos sin bloquear la app."""
        async with warm_lock:
            try:
                result = seed_service.load()
                if result.missing_products or result.skipped_products:
                    logger.warning(
                        "Seed cargado con %s productos ausentes y %s no mapeables",
                        len(result.missing_products),
                        len(result.skipped_products),
                    )
            except Exception:  # noqa: BLE001 - la app debe arrancar sin seed
                logger.exception("No se pudo cargar el seed de ingredientes y platos")

            if resolved.app_env == "test":
                return
            try:
                allergen_result = await allergen_service.run()
                logger.info(
                    "Alérgenos actualizados en %s productos (%s fallos)",
                    allergen_result.updated,
                    len(allergen_result.failed),
                )
            except Exception:  # noqa: BLE001 - sin red se conserva lo anterior
                logger.warning("No se pudieron actualizar los alérgenos", exc_info=True)

    sync_service = CatalogSyncService(
        factory,
        on_sync_finished=lambda _result: warm_data(),
    )

    @asynccontextmanager
    async def lifespan(_application: FastAPI) -> AsyncIterator[None]:
        warm_task: asyncio.Task[None] | None = None
        try:
            sync_service.recover_interrupted_runs()
        except Exception:  # noqa: BLE001 - una base sin migrar no debe impedir arrancar
            logger.warning("No se pudieron recuperar syncs interrumpidas", exc_info=True)

        if resolved.app_env != "test":
            started = False
            if resolved.sync_on_startup:
                try:
                    started = sync_service.start_if_due() is not None
                except Exception:  # noqa: BLE001 - arrancar sin red sigue siendo válido
                    logger.warning("No se pudo lanzar la sync de arranque", exc_info=True)
            if not started:
                warm_task = asyncio.create_task(warm_data(), name="seed-warmup")

        yield

        if warm_task is not None:
            warm_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await warm_task
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
    application.state.seed_service = seed_service
    application.state.allergen_sync = allergen_service
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
    application.include_router(domain.router, prefix=API_PREFIX)
    return application


app = create_app()
