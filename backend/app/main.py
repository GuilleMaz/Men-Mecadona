"""Punto de entrada de la API de Cesta."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health
from app.config import APP_NAME, APP_VERSION, Settings, get_settings

API_PREFIX = "/api"


def create_app(settings: Settings | None = None) -> FastAPI:
    """Construye la aplicación FastAPI.

    CORS solo se activa en desarrollo y solo para el origen del servidor de Vite.
    """
    resolved = settings or get_settings()
    application = FastAPI(
        title=APP_NAME,
        version=APP_VERSION,
        description=(
            "API local para generar menús de comida y cena para N personas, N días "
            "y un presupuesto, con precios de la tienda online de Mercadona."
        ),
    )

    cors_origins = resolved.cors_origins
    if cors_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["*"],
        )

    application.include_router(health.router, prefix=API_PREFIX)
    return application


app = create_app()
