#Requires -Version 5.1
<#
.SYNOPSIS
    Audita dependencias de backend y frontend (F5.3).

.DESCRIPTION
    Ejecuta pip-audit sobre el entorno de uv y npm audit con umbral high.
    No forma parte de check.ps1 porque necesita red y tarda más.

.EXAMPLE
    .\audit.ps1
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

try {
    Push-Location (Join-Path $root "backend")
    try {
        Invoke-Checked "Backend: pip-audit" { uv run --with pip-audit pip-audit --progress-spinner off }
    } finally {
        Pop-Location
    }

    Push-Location (Join-Path $root "frontend")
    try {
        Invoke-Checked "Frontend: npm audit (high/critical)" { npm audit --audit-level=high }
    } finally {
        Pop-Location
    }

    Write-Host ""
    Write-Host "Auditoria completada sin hallazgos high/critical." -ForegroundColor Green
} catch {
    Write-Host ""
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
