"""Endpoint de salud."""

from fastapi import APIRouter

from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Estado del servicio")
def read_health() -> HealthResponse:
    """Devuelve `{"status": "ok"}` cuando la API está operativa."""
    return HealthResponse()
