# PerioVision AI - Windows helper with the same targets as the Makefile.
# Usage (from the repository root):
#   .\run.ps1 setup | backend | frontend | test | demo | lint | docs
#   .\run.ps1 install-models -From <folder downloaded from Colab>
#   Production:  make-prod-env | mongo | create-admin | prod | frontend-prod | resign-prod
param(
    [Parameter(Mandatory = $true)][ValidateSet("setup", "backend", "frontend", "test", "demo", "lint", "docs", "install-models",
        "make-prod-env", "mongo", "create-admin", "prod", "frontend-prod", "resign-prod")][string]$Target,
    [string]$From
)
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
function Use-Production {
    if (-not (Test-Path "$Root\.env.production")) { throw "No .env.production yet. Run: .\run.ps1 make-prod-env" }
    $env:ENV_FILE = "$Root\.env.production"
    Remove-Item Env:DB_MODE -ErrorAction SilentlyContinue
}
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
    "install-models" {
        if (-not $From) { throw "Pass the export folder: .\run.ps1 install-models -From `"$HOME\Downloads\export`"" }
        Push-Location "$Root\backend"
        python scripts/install_trained_weights.py --from "$From"
        if ($LASTEXITCODE -eq 0) { python -m pytest -q }
        Pop-Location
        if (Test-Path "$Root\.env.production") { Write-Host "Production copy: run .\run.ps1 resign-prod to copy and sign these weights for production." }
    }
    # ---------- production ----------
    "make-prod-env" { Push-Location "$Root\backend"; python scripts/make_production_env.py; Pop-Location }
    "resign-prod" { Push-Location "$Root\backend"; python scripts/make_production_env.py --resign; Pop-Location }
    "mongo" {
        # MongoDB with a password, on this machine only (needs Docker Desktop running)
        docker compose --env-file "$Root\.env.production" up -d mongodb
    }
    "create-admin" {
        Use-Production
        Push-Location "$Root\backend"; python scripts/create_admin.py; Pop-Location
    }
    "prod" {
        Use-Production
        Push-Location "$Root\backend"
        Write-Host "PerioVision (live mode) on http://127.0.0.1:5000 via waitress. Put an HTTPS reverse proxy in front for real use."
        python -m waitress --host=127.0.0.1 --port=5000 --threads=8 --ident=PerioVision wsgi:app
        Pop-Location
    }
    "frontend-prod" {
        # Production build, served on http://localhost:4173 with /api proxied to the backend
        Push-Location "$Root\frontend"; npm run build; npx vite preview; Pop-Location
    }
}
