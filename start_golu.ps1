# Project Golu: PowerShell Production Launcher
$Host.UI.RawUI.WindowTitle = "Project Golu: Zero-Cloud Local AI Orchestrator"
Set-Location $PSScriptRoot
Write-Host "Launching Project Golu (4GB VRAM Edition)..." -ForegroundColor Cyan
python start_golu.py
