# Seguridad local de Cesta

Cesta es una aplicaciÃ³n local de un solo usuario. No hay login ni exposiciÃ³n a la
LAN en el MVP. Esta checklist cubre F0-F6.

## Checklist

- [x] El backend escucha solo en `127.0.0.1`; `run.ps1` pasa `--host 127.0.0.1` tambiÃ©n en `-Prod`.
- [x] CORS solo se activa en desarrollo y solo para `http://localhost:5173`.
- [x] En producciÃ³n no se aÃ±ade CORS y `/docs`/`/redoc` quedan desactivados.
- [x] El middleware de `Host` acepta solo `127.0.0.1`, `localhost` y `::1`; el puerto se ignora.
- [x] Un `Host` desconocido devuelve `400 INVALID_HOST` con el formato de error de la API.
- [x] `.env` estÃ¡ ignorado por git; `.env.example` no contiene secretos.
- [x] No hay credenciales de Mercadona, automatizaciÃ³n de compra ni telemetrÃ­a.
- [x] La base SQLite vive fuera de OneDrive y se rechaza una ruta de datos dentro de OneDrive.
- [x] SQLite usa WAL, `foreign_keys=ON` y `busy_timeout=5000`.
- [x] Las Ãºnicas llamadas externas son las de lectura del catÃ¡logo de Mercadona.
- [x] La app no se expone en LAN; el acceso mÃ³vil queda fuera del MVP.
- [x] Los tests no llaman a Mercadona ni a servicios externos.
- [x] El export CSV neutraliza fÃ³rmulas (`=`, `+`, `-`, `@`) y escapa comillas, comas y saltos.
- [x] Las respuestas de la API no exponen `raw_json`, credenciales ni detalles internos del catÃ¡logo.
- [x] `pip-audit` no encontrÃ³ vulnerabilidades y `npm audit --audit-level=high` devolviÃ³ 0 hallazgos.
- [x] Los lockfiles (`backend/uv.lock`, `frontend/package-lock.json`) se versionan.
- [x] Backup verificado con `PRAGMA integrity_check`; restauraciÃ³n atÃ³mica y con `--force` explÃ­cito.
- [x] La copia local de precios solo se usa si es de CP 22002 / almacÃ©n 4389; una sync de otro almacÃ©n no se mezcla.
- [x] Un test estÃ¡tico comprueba que no hay telemetrÃ­a, `sendBeacon`, `WebSocket` ni hosts externos no declarados.
- [x] El contrato Â«sin pasos de cocinaÂ» se comprueba sobre `dishes.yaml` y las respuestas de menÃº.

## Comprobaciones automÃ¡ticas

```powershell
cd backend
uv run pytest tests\test_security.py tests\test_cors.py tests\test_config.py tests\test_delivery.py tests\test_backup_restore.py tests\test_production_build.py
```

Los tests cubren hosts permitidos y rechazados, CORS en desarrollo y producciÃ³n,
rechazo de bases dentro de OneDrive, privacidad, contrato sin pasos, backup,
restauraciÃ³n y servido del build.

## AuditorÃ­a de dependencias

```powershell
.\audit.ps1
```

El script ejecuta `pip-audit` en el entorno de `uv` y `npm audit --audit-level=high`.
Ãšltima ejecuciÃ³n: 0 vulnerabilidades conocidas y 0 hallazgos high/critical.

## Backup y restauraciÃ³n

```powershell
cd backend
uv run python ..\scripts\backup_db.py
uv run python ..\scripts\restore_db.py --backup <ruta> --force
```

DetÃ©n la app antes de restaurar. El script rechaza una copia que no pase
`integrity_check` o que no tenga el esquema de Cesta, y elimina `-wal`/`-shm`
antiguos solo con `--force`.
