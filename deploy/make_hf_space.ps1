# Publish the PerioVision backend (demo mode) to a Hugging Face Docker Space.
# Usage (from the repository root, after creating an EMPTY Docker Space on huggingface.co):
#   .\deploy\make_hf_space.ps1 -Space <your-hf-username>/periovision
# Uses only COMMITTED files (git archive), so .env, private keys and production data never leave this machine.
# git asks for your Hugging Face username and an access token (write) as the password when it pushes.
param([Parameter(Mandatory = $true)][string]$Space)
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$Out = Join-Path $env:USERPROFILE "Downloads\periovision-space"
if (Test-Path $Out) { throw "$Out already exists. Rename or remove it first." }
if (git -C $Root status --porcelain -- backend .env.example) { throw "backend/ has uncommitted changes. Commit them first (the Space is built from the last commit)." }

$zip = Join-Path $env:TEMP "periovision-space.zip"
git -C $Root archive --format=zip -o $zip HEAD backend .env.example
Expand-Archive $zip $Out; Remove-Item $zip
Copy-Item "$PSScriptRoot\huggingface\Dockerfile", "$PSScriptRoot\huggingface\README.md" $Out

Push-Location $Out
git init -b main | Out-Null
git lfs install --local | Out-Null
git lfs track "*.pt" | Out-Null       # Hugging Face refuses plain git files over 10 MB
git add .gitattributes; git add .
git commit -q -m "PerioVision backend (demo mode)"
git remote add origin "https://huggingface.co/spaces/$Space"
git push --force -u origin main        # replaces the new Space's placeholder commit
Pop-Location
Write-Host "Pushed. The Space builds in ~10 minutes: https://huggingface.co/spaces/$Space"
Write-Host "Its API URL is https://$($Space.Replace('/', '-').ToLower()).hf.space  (check: <that URL>/health)"
