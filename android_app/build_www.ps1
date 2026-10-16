# Copy web frontend from parent project to www/
$src = Join-Path $PSScriptRoot ".."
$dst = Join-Path $PSScriptRoot "www"

if (Test-Path $dst) {
    Remove-Item -Recurse -Force $dst
}
New-Item -ItemType Directory -Path $dst | Out-Null

# Copy index.html
Copy-Item (Join-Path $src "index.html") $dst

# Copy assets
Copy-Item -Recurse (Join-Path $src "assets") $dst

Write-Host "Web frontend copied to www/"
Write-Host "Files in www/:"
Get-ChildItem $dst | Select-Object Name
