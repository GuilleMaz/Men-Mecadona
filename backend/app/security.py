"""Seguridad local: validación de la cabecera `Host`.

La app escucha solo en `127.0.0.1`, pero un navegador puede enviar un `Host`
arbitrario (por ejemplo, tras un ataque de DNS rebinding). El middleware acepta
únicamente hosts locales y devuelve un error homogéneo para el resto.
"""

from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

INVALID_HOST = "INVALID_HOST"


def hostname_from_header(header: str | None) -> str | None:
    """Extrae el nombre de host de un `Host` con puerto opcional o IPv6 entre corchetes."""
    if header is None:
        return None
    value = header.strip().lower()
    if not value or any(character in value for character in " \t,/@"):
        return None
    try:
        parsed = urlsplit(f"//{value}")
    except ValueError:
        return None
    return parsed.hostname


class HostValidationMiddleware(BaseHTTPMiddleware):
    """Rechaza peticiones cuyo `Host` no esté en la allowlist local."""

    def __init__(self, app: ASGIApp, allowed_hosts: Iterable[str]) -> None:
        super().__init__(app)
        self.allowed_hosts = frozenset(host.lower() for host in allowed_hosts)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        hostname = hostname_from_header(request.headers.get("host"))
        if hostname is None or hostname not in self.allowed_hosts:
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": INVALID_HOST,
                        "message": "Host no permitido. Usa 127.0.0.1 o localhost.",
                        "details": {},
                    }
                },
            )
        return await call_next(request)
