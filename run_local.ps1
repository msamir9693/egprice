# Refresh prices from this PC and rebuild the site.
# Usage (PowerShell, from anywhere):  powershell -ExecutionPolicy Bypass -File run_local.ps1
# If this folder is a git repo with a GitHub remote, the new data/ and docs/ are pushed too.
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

python engine.py
if ($LASTEXITCODE -ne 0) { Write-Host "engine.py failed - see data\run.log"; exit 1 }
python build_site.py
if ($LASTEXITCODE -ne 0) { Write-Host "build_site.py failed"; exit 1 }

$git = Get-Command git -ErrorAction SilentlyContinue
if ($git -and (Test-Path ".git")) {
    git add data docs
    git diff --cached --quiet
    if ($LASTEXITCODE -ne 0) {
        git commit -m "Refresh prices $(Get-Date -Format 'yyyy-MM-dd')"
        git push
    } else {
        Write-Host "No price changes to publish."
    }
} else {
    Write-Host "Site built in docs\index.html (git not set up, so nothing was published)."
}
