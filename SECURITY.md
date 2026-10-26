# Seguridad local de Cesta

Cesta es una aplicación local de un solo usuario. No hay login ni exposición a la
LAN en el MVP. Esta checklist cubre la F0 y se revisará en F5.

## Checklist

- [x] El backend escucha solo en `127.0.0.1`; `run.ps1` pasa `--host 127.0.0.1`.
- [x] CORS solo se activa en desarrollo y solo para `http://localhost:5173`.
- [x] En producción no se añade CORS.
- [x] El middleware de `Host` acepta solo `127.0.0.1`, `localhost` y `::1`; el puerto se ignora.
- [x] Un `Host` desconocido devuelve `400 INVALID_HOST` con el formato de error de la API.
- [x] `.env` está ignorado por git; `.env.example` no contiene secretos.
- [x] No hay credenciales de Mercadona, automatización de compra ni telemetría.
- [x] La base SQLite vive fuera de OneDrive y se rechaza una ruta de datos dentro de OneDrive.
- [x] SQLite usa WAL, `foreign_keys=ON` y `busy_timeout=5000`.
- [x] Las únicas llamadas externas son las de lectura del catálogo de Mercadona.
- [x] La app no se expone en LAN; el acceso móvil queda fuera del MVP.
- [x] Los tests no llaman a Mercadona ni a servicios externos.

## Comprobaciones automáticas

```powershell
cd backend
uv run pytest tests\test_security.py tests\test_cors.py tests\test_config.py
```

Los tests cubren hosts permitidos y rechazados, CORS en desarrollo y producción,
y el rechazo de bases de datos dentro de OneDrive.
