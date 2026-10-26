"""Servido del frontend compilado desde FastAPI en producción local (F5.6).

En desarrollo, Vite sirve la UI y hace proxy de `/api`. En producción local,
`npm run build` genera `frontend/dist` y FastAPI sirve esos archivos en el mismo
puerto que la API. Las rutas del cliente (`/menus/1`, `/history`…) deben devolver
`index.html`; los recursos con extensión y las rutas `/api/*` desconocidas no.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.types import Scope

logger = logging.getLogger(__name__)


class SPAStaticFiles(StaticFiles):
    """`StaticFiles` con fallback a `index.html` para rutas del cliente."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            # No se sirve la SPA para una API inexistente ni para un recurso con
            # extensión que no existe: eso ocultaría errores reales. Las rutas de
            # documentación quedan desactivadas en producción.
            normalized = path.replace("\\", "/").lstrip("/")
            if (
                normalized.startswith("api/")
                or normalized in {"docs", "redoc", "openapi.json"}
                or "." in Path(normalized).name
            ):
                raise
            return await super().get_response("index.html", scope)


def mount_frontend(application: FastAPI, dist: Path) -> bool:
    """Monta `dist` en `/` si existe; devuelve si se montó."""
    index = dist / "index.html"
    if not index.is_file():
        logger.error(
            "No se encontró el frontend compilado en %s. Ejecuta 'npm run build'.",
            dist,
        )
        return False
    application.mount("/", SPAStaticFiles(directory=dist, html=True), name="frontend")
    logger.info("Frontend compilado servido desde %s", dist)
    return True
