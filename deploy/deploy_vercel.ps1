# Deploy the web app to Vercel, with /api forwarded to the backend.
# Usage (from the repository root):  .\deploy\deploy_vercel.ps1 -BackendUrl https://<user>-periovision.hf.space
# The first run asks you to log in to Vercel in the browser and to confirm the project settings.
param([Parameter(Mandatory = $true)][string]$BackendUrl)
$ErrorActionPreference = "Stop"
$BackendUrl = $BackendUrl.TrimEnd("/")
if ($BackendUrl -notmatch '^https://[A-Za-z0-9.-]+$') { throw "BackendUrl must look like https://name.hf.space (no path)." }
$Root = Split-Path $PSScriptRoot -Parent
$cfg = Join-Path $Root "frontend\vercel.json"
$text = Get-Content $cfg -Raw
$text = [regex]::Replace($text, '"destination": "https://[^"/]+/api/:path\*"', "`"destination`": `"$BackendUrl/api/:path*`"")
[IO.File]::WriteAllText($cfg, $text)
Write-Host "frontend/vercel.json now forwards /api to $BackendUrl"
Push-Location (Join-Path $Root "frontend")
npx --yes vercel@latest --prod
Pop-Location
