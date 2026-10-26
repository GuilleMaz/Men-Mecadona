#Requires -Version 5.1
<#
.SYNOPSIS
    Cierra una fase: ejecuta la calidad, hace commit y lo sube a GitHub.

.DESCRIPTION
    Gate reproducible para cerrar una fase del proyecto:

    1. Ejecuta `check.ps1` (lint, formato, tipos, tests y build).
    2. Comprueba que no se cuelan secretos, bases de datos ni dependencias.
    3. Hace `git add -A` y un commit `FASE: resumen`.
    4. Sube el commit a `origin` (o al remoto indicado).

    Si la calidad falla, no se hace commit. Si el push falla, el commit queda
    local y el script termina con error para que se pueda reintentar.

.PARAMETER Phase
    Identificador de fase, por ejemplo `F0` o `F1`.

.PARAMETER Summary
    Resumen corto para el mensaje de commit.

.PARAMETER Remote
    Remoto de git. Por defecto `origin`.

.PARAMETER Branch
    Rama a subir. Por defecto, la rama actual.

.PARAMETER SkipChecks
    Omite `check.ps1`. Solo para emergencias documentadas.

.PARAMETER NoPush
    Hace el commit pero no sube nada. No es el flujo normal de cierre.

.EXAMPLE
    .\finish-phase.ps1 -Phase F0 -Summary "fundaciones y spikes"

.EXAMPLE
    .\finish-phase.ps1 F1 "catalogo y sincronizacion"
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidatePattern('^F[0-9]+(\.[0-9]+)?$')]
    [string]$Phase,

    [Parameter(Position = 1)]
    [string]$Summary = "cierre de fase",

    [string]$Remote = "origin",

    [string]$Branch,

    [switch]$SkipChecks,

    [switch]$NoPush
)

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
    & git rev-parse --is-inside-work-tree *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "El directorio actual no es un repositorio git."
    }

    $currentBranch = (& git rev-parse --abbrev-ref HEAD).Trim()
    if ($currentBranch -eq "HEAD") {
        throw "La rama esta en detached HEAD; cambia a una rama antes de cerrar la fase."
    }
    if (-not $Branch) {
        $Branch = $currentBranch
    }
    if ($Branch -ne $currentBranch) {
        throw "La rama actual es '$currentBranch' y se intenta subir '$Branch'."
    }

    & git remote get-url $Remote *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "El remoto '$Remote' no existe. Configura GitHub antes de cerrar la fase."
    }

    if (-not $SkipChecks) {
        $checkScript = Join-Path $root "check.ps1"
        if (-not (Test-Path -LiteralPath $checkScript)) {
            throw "No se encuentra check.ps1 en $root."
        }
        Write-Step "Ejecutando check.ps1"
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $checkScript
        if ($LASTEXITCODE -ne 0) {
            throw "check.ps1 ha fallado; no se hace commit."
        }
    } else {
        Write-Host "[AVISO] check.ps1 omitido con -SkipChecks." -ForegroundColor Yellow
    }

    $workingChanges = @(& git status --porcelain | Where-Object { $_ })
    $commitCreated = $false

    if ($workingChanges.Count -gt 0) {
        Write-Step "Preparando cambios"
        & git add -A
        if ($LASTEXITCODE -ne 0) {
            throw "git add ha fallado."
        }

        $staged = @(& git diff --cached --name-only | Where-Object { $_ })
        $forbiddenPatterns = @(
            '(^|/)\.env$',
            '(^|/)\.env\.(?!example$).+$',
            '\.(db|sqlite|sqlite3|db-wal|db-shm|db-journal)$',
            '(^|/)node_modules/',
            '(^|/)\.venv/',
            '(^|/)frontend/dist/',
            '(^|/)__pycache__/',
            '\.(pem|key|pfx|p12)$'
        )
        $forbidden = @()
        foreach ($path in $staged) {
            foreach ($pattern in $forbiddenPatterns) {
                if ($path -match $pattern) {
                    $forbidden += $path
                    break
                }
            }
        }
        if ($forbidden.Count -gt 0) {
            & git reset --quiet
            throw "Hay archivos prohibidos en el commit:`n$($forbidden -join "`n")"
        }

        $staged = @(& git diff --cached --name-only | Where-Object { $_ })
        if ($staged.Count -eq 0) {
            Write-Host "No hay cambios preparados para commitear." -ForegroundColor Yellow
        } else {
            $message = "${Phase}: $Summary"
            Write-Step "Creando commit: $message"
            & git commit -m $message -m "Cierre de fase verificado con check.ps1."
            if ($LASTEXITCODE -ne 0) {
                throw "git commit ha fallado."
            }
            $commitCreated = $true
        }
    } else {
        Write-Host "No hay cambios en el arbol de trabajo." -ForegroundColor Yellow
    }

    if ($NoPush) {
        Write-Host "[AVISO] Commit creado sin push por -NoPush." -ForegroundColor Yellow
    } else {
        $upstream = & git rev-parse --abbrev-ref --symbolic-full-name "@{u}" 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $upstream) {
            Invoke-Checked "Subiendo a $Remote/$Branch (nuevo upstream)" { git push -u $Remote $Branch }
        } else {
            Invoke-Checked "Subiendo a $Remote/$Branch" { git push $Remote $Branch }
        }
    }

    $head = (& git rev-parse --short HEAD).Trim()
    $subject = (& git log -1 --pretty=%s).Trim()
    Write-Host ""
    if ($commitCreated) {
        Write-Host "Fase $Phase cerrada: $head $subject" -ForegroundColor Green
    } else {
        Write-Host "Sin commit nuevo; HEAD sigue en $head $subject" -ForegroundColor Green
    }
    if (-not $NoPush) {
        Write-Host "GitHub actualizado en $Remote/$Branch." -ForegroundColor Green
    }
} catch {
    Write-Host ""
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
