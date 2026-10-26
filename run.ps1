#Requires -Version 5.1
<#
.SYNOPSIS
    Arranca Cesta en local: backend FastAPI + frontend Vite.

.DESCRIPTION
    Resuelve CESTA_DATA_DIR (por defecto %LOCALAPPDATA%\Cesta), crea la base
    SQLite fuera de OneDrive y arranca ambos servicios escuchando solo en local.

.EXAMPLE
    .\run.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\run.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location -LiteralPath $root

function Write-Step {
    param([string]$Message)
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Resolve-CestaDataDir {
    if ($env:CESTA_DATA_DIR) {
        if (-not [System.IO.Path]::IsPathRooted($env:CESTA_DATA_DIR)) {
            throw "CESTA_DATA_DIR debe ser una ruta absoluta."
        }
        $path = [System.IO.Path]::GetFullPath($env:CESTA_DATA_DIR)
    } else {
        if (-not $env:LOCALAPPDATA) {
            throw "LOCALAPPDATA no esta definido. Configura CESTA_DATA_DIR con una ruta absoluta."
        }
        $path = Join-Path $env:LOCALAPPDATA "Cesta"
    }

    if ($path -match '(?i)onedrive') {
        throw "La base de datos no puede vivir en OneDrive: $path"
    }
    if (-not (Test-Path -LiteralPath $path)) {
        New-Item -ItemType Directory -Path $path -Force | Out-Null
    }
    return $path
}

function Wait-Backend {
    param(
        [System.Diagnostics.Process]$Process,
        [int]$TimeoutSeconds = 60
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if ($Process.HasExited) {
            throw "El backend se ha detenido antes de estar listo (codigo $($Process.ExitCode))."
        }
        try {
            $response = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" -TimeoutSec 2
            if ($response.status -eq "ok") {
                return
            }
        } catch {
            # El backend aun no esta listo; se reintenta hasta el deadline.
        }
        Start-Sleep -Milliseconds 500
    }
    throw "El backend no responde en http://127.0.0.1:8000/api/health"
}

function Stop-ProcessTree {
    param([System.Diagnostics.Process]$Process)
    if ($null -eq $Process -or $Process.HasExited) {
        return
    }
    & taskkill.exe /T /F /PID $Process.Id *> $null
}

$backend = $null
$frontend = $null
try {
    $dataDir = Resolve-CestaDataDir
    $env:CESTA_DATA_DIR = $dataDir
    Write-Step "Datos en $dataDir (fuera de OneDrive)"

    $uv = (Get-Command uv -CommandType Application -ErrorAction Stop).Source
    $npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if ($null -eq $npmCommand) {
        $npmCommand = Get-Command npm -ErrorAction Stop
    }
    $npm = $npmCommand.Source

    if (-not (Test-Path -LiteralPath (Join-Path $root "backend\.venv"))) {
        Write-Step "Sincronizando dependencias del backend (uv sync)"
        Push-Location (Join-Path $root "backend")
        try {
            & $uv sync
            if ($LASTEXITCODE -ne 0) { throw "uv sync ha fallado (codigo $LASTEXITCODE)." }
        } finally {
            Pop-Location
        }
    }

    if (-not (Test-Path -LiteralPath (Join-Path $root "frontend\node_modules"))) {
        Write-Step "Instalando dependencias del frontend (npm install)"
        Push-Location (Join-Path $root "frontend")
        try {
            & $npm install
            if ($LASTEXITCODE -ne 0) { throw "npm install ha fallado (codigo $LASTEXITCODE)." }
        } finally {
            Pop-Location
        }
    }

    Write-Step "Inicializando la base de datos"
    Push-Location (Join-Path $root "backend")
    try {
        & $uv run python ..\scripts\init_db.py
        if ($LASTEXITCODE -ne 0) {
            throw "La inicializacion de la base de datos ha fallado (codigo $LASTEXITCODE)."
        }

        Write-Step "Aplicando migraciones"
        & $uv run alembic upgrade head
        if ($LASTEXITCODE -ne 0) {
            throw "Las migraciones han fallado (codigo $LASTEXITCODE)."
        }
    } finally {
        Pop-Location
    }

    Write-Step "Arrancando backend en http://127.0.0.1:8000"
    $backend = Start-Process -FilePath $uv `
        -ArgumentList @(
            "run", "uvicorn", "app.main:app", "--reload",
            "--host", "127.0.0.1", "--port", "8000"
        ) `
        -WorkingDirectory (Join-Path $root "backend") -PassThru -NoNewWindow

    Wait-Backend -Process $backend
    Write-Step "Backend listo"

    Write-Step "Arrancando frontend en http://localhost:5173"
    $frontend = Start-Process -FilePath $npm `
        -ArgumentList @("run", "dev") `
        -WorkingDirectory (Join-Path $root "frontend") -PassThru -NoNewWindow

    Write-Host ""
    Write-Host "Cesta en marcha:" -ForegroundColor Green
    Write-Host "  UI:  http://localhost:5173"
    Write-Host "  API: http://127.0.0.1:8000/api/health"
    Write-Host "Pulsa Ctrl+C para detener ambos servicios."
    Write-Host ""

    while ($true) {
        if ($backend.HasExited) {
            throw "El backend se ha detenido (codigo $($backend.ExitCode))."
        }
        if ($frontend.HasExited) {
            throw "El frontend se ha detenido (codigo $($frontend.ExitCode))."
        }
        Start-Sleep -Seconds 1
    }
} finally {
    Write-Step "Deteniendo servicios"
    if ($null -ne $frontend) {
        Stop-ProcessTree -Process $frontend
    }
    if ($null -ne $backend) {
        Stop-ProcessTree -Process $backend
    }
}
