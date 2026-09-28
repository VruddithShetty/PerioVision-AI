# PerioVision AI - Windows helper with the same targets as the Makefile.
# Usage (from the repository root):  .\run.ps1 setup | backend | frontend | test | demo | lint | docs
param([Parameter(Mandatory = $true)][ValidateSet("setup", "backend", "frontend", "test", "demo", "lint", "docs")][string]$Target)
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
switch ($Target) {
    "setup" {
        Push-Location "$Root\backend"; python -m pip install -r requirements-dev.txt; Pop-Location
        if (-not (Test-Path "$Root\.env")) { Copy-Item "$Root\.env.example" "$Root\.env"; Write-Host "Created .env from .env.example - edit the values" }
        if (Test-Path "$Root\frontend\package.json") { Push-Location "$Root\frontend"; npm install; Pop-Location }
    }
    "backend" { Push-Location "$Root\backend"; python wsgi.py; Pop-Location }
    "frontend" { Push-Location "$Root\frontend"; npm run dev; Pop-Location }
    "test" { Push-Location "$Root\backend"; python -m pytest -q; Pop-Location }
    "lint" {
        Push-Location "$Root\backend"; python -m ruff check .; Pop-Location
        Push-Location "$Root\frontend"; npm run lint; Pop-Location
    }
    "docs" { Push-Location "$Root\backend"; python scripts/generate_api_docs.py; Pop-Location }
    "demo" { $env:DB_MODE = "demo"; Push-Location "$Root\backend"; python wsgi.py; Pop-Location }
}
