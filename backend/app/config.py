"""Configuración de la aplicación.

Los valores se leen de variables de entorno y, si existe, de un `.env` en la raíz
del repositorio o en `backend/`. Ver `PLAN.md` §16.2.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_NAME = "Cesta"
APP_VERSION = "0.1.0"

#: Código postal del MVP. Es una constante del producto, no se configura por entorno.
POSTAL_CODE = "22002"
#: Almacén esperado para el CP 22002. Si no se confirma, no se generan menús.
EXPECTED_WAREHOUSE = "4389"

#: Orígenes permitidos en desarrollo: solo el servidor de Vite.
DEV_CORS_ORIGINS: tuple[str, ...] = ("http://localhost:5173",)
#: Entornos que habilitan CORS para el frontend de desarrollo.
DEV_ENVIRONMENTS: frozenset[str] = frozenset({"local", "development", "dev", "test"})
#: Hosts locales permitidos. El puerto se ignora al validar la cabecera Host.
LOCAL_HOSTS: frozenset[str] = frozenset({"127.0.0.1", "localhost", "::1"})

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
_ENV_FILES = (PROJECT_ROOT / ".env", BACKEND_DIR / ".env")


class Settings(BaseSettings):
    """Ajustes de ejecución de la app."""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["local", "development", "production", "test"] = "local"
    sync_on_startup: bool = True
    optimizer_time_limit_seconds: int = Field(default=8, ge=1, le=60)
    cesta_data_dir: Path | None = None

    @model_validator(mode="after")
    def _resolve_data_dir(self) -> Self:
        """Resuelve el directorio de datos, rechaza rutas relativas y OneDrive."""
        if self.cesta_data_dir is None:
            local_app_data = os.environ.get("LOCALAPPDATA")
            if not local_app_data:
                raise ValueError(
                    "LOCALAPPDATA no está definido; configura CESTA_DATA_DIR con una ruta absoluta"
                )
            self.cesta_data_dir = Path(local_app_data) / "Cesta"
        elif not self.cesta_data_dir.is_absolute():
            raise ValueError("CESTA_DATA_DIR debe ser una ruta absoluta")

        if any(part.casefold() == "onedrive" for part in self.cesta_data_dir.parts):
            raise ValueError("CESTA_DATA_DIR no puede estar dentro de OneDrive")
        return self

    @property
    def data_dir(self) -> Path:
        """Directorio de datos resuelto (por defecto, fuera de OneDrive)."""
        if self.cesta_data_dir is None:  # pragma: no cover - lo garantiza el validador
            raise RuntimeError("CESTA_DATA_DIR no está resuelto")
        return self.cesta_data_dir

    @property
    def database_path(self) -> Path:
        """Ruta absoluta del archivo SQLite."""
        return self.data_dir / "cesta.db"

    @property
    def database_url(self) -> str:
        """URL de SQLAlchemy con ruta absoluta en formato POSIX."""
        return f"sqlite:///{self.database_path.as_posix()}"

    @property
    def frontend_dist(self) -> Path:
        """Directorio del frontend compilado servido en producción local."""
        return PROJECT_ROOT / "frontend" / "dist"

    @property
    def is_development(self) -> bool:
        return self.app_env in DEV_ENVIRONMENTS

    @property
    def cors_origins(self) -> list[str]:
        """CORS solo en desarrollo y solo para el puerto de Vite."""
        return list(DEV_CORS_ORIGINS) if self.is_development else []

    @property
    def allowed_hosts(self) -> frozenset[str]:
        """Hosts locales aceptados; cualquier otro Host se rechaza con 400."""
        return LOCAL_HOSTS


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Devuelve los ajustes cacheados del proceso."""
    return Settings()
