[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

python -m pip install pyinstaller
pyinstaller --noconsole --onefile --name "BIPPreviewRepairPro" "bip_preview_repair_pro.pyw"

Write-Host ""
Write-Host "Build complete:"
Write-Host (Join-Path $root "dist\BIPPreviewRepairPro.exe")
