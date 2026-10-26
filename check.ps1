#Requires -Version 5.1
<#
.SYNOPSIS
    Ejecuta lint, tipos, tests y build de backend y frontend.

.DESCRIPTION
    Un solo comando para comprobar que el repositorio sigue en verde:
    Ruff, mypy y pytest en backend; ESLint, Prettier, TypeScript, Vitest y
    build en frontend. Tambien revisa los scripts de Python de la raiz.

.EXAMPLE
    .\check.ps1
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

function Invoke-Checked {
    param(
        [string]$Label,
        [scriptblock]$Command
    )
    Write-Step $Label
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Fallo en '$Label' (codigo $LASTEXITCODE)."
    }
}

$started = Get-Date
try {
    Push-Location (Join-Path $root "backend")
    try {
        Invoke-Checked "Backend: Ruff" { uv run ruff check . }
        Invoke-Checked "Backend: formato" { uv run ruff format --check . }
        Invoke-Checked "Backend: mypy" { uv run mypy app }
        Invoke-Checked "Backend: pytest" { uv run pytest }
        Invoke-Checked "Scripts: Ruff" { uv run ruff check --config pyproject.toml ..\scripts }
        Invoke-Checked "Scripts: formato" { uv run ruff format --check --config pyproject.toml ..\scripts }
    } finally {
        Pop-Location
    }

    Push-Location (Join-Path $root "frontend")
    try {
        Invoke-Checked "Frontend: ESLint" { npm run lint }
        Invoke-Checked "Frontend: Prettier" { npm run format:check }
        Invoke-Checked "Frontend: TypeScript" { npm run typecheck }
        Invoke-Checked "Frontend: Vitest" { npm run test }
        Invoke-Checked "Frontend: build" { npm run build }
    } finally {
        Pop-Location
    }

    $elapsed = (Get-Date) - $started
    Write-Host ""
    Write-Host ("Todo en verde en {0:N1} s." -f $elapsed.TotalSeconds) -ForegroundColor Green
} catch {
    Write-Host ""
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
