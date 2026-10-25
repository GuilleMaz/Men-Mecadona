"""Esquemas de salud del servicio."""

from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Respuesta de `GET /api/health`."""

    status: Literal["ok"] = Field(default="ok", description="Estado del servicio")
