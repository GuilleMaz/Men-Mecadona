# Backend de Cesta

API local en FastAPI + SQLite. Se ejecuta solo en `127.0.0.1`.

```powershell
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

- Salud: `GET http://127.0.0.1:8000/api/health` → `{"status":"ok"}`.
- Documentación interactiva: `http://127.0.0.1:8000/docs`.

Calidad:

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy app
uv run pytest
```

La base de datos vive en `%LOCALAPPDATA%\Cesta\cesta.db` (o en `CESTA_DATA_DIR`),
fuera de OneDrive. Los YAML de ingredientes y platos irán en `app/data/`.
