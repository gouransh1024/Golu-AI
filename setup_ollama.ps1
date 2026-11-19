# Project Golu: Ollama Installer & Model Pull Automation
# Usage: powershell -ExecutionPolicy Bypass -File setup_ollama.ps1

$installer = "C:\Users\goura\Downloads\OllamaSetup.exe"

if (Test-Path $installer) {
    Write-Host "Found Ollama installer at $installer. Starting installation..." -ForegroundColor Cyan
    Start-Process -FilePath $installer -ArgumentList "/silent" -Wait
    Write-Host "Ollama installation completed." -ForegroundColor Green
} else {
    Write-Host "Installer not found at $installer. Ensure download completes first." -ForegroundColor Yellow
}

# Wait for Ollama service to become responsive on localhost:11434
$maxRetries = 20
$retry = 0
$ollamaReady = $false

Write-Host "Checking Ollama localhost:11434 status..." -ForegroundColor Cyan
while ($retry -lt $maxRetries) {
    try {
        $resp = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 2 -ErrorAction Stop
        $ollamaReady = $true
        Write-Host "Ollama is online and responsive!" -ForegroundColor Green
        break
    } catch {
        Start-Sleep -Seconds 2
        $retry++
    }
}

if ($ollamaReady) {
    Write-Host "Pulling primary model (qwen2.5:3b or qwen2.5:1.5b for 4GB VRAM)..." -ForegroundColor Cyan
    ollama pull qwen2.5:3b
    Write-Host "Pulling embedding model (all-minilm)..." -ForegroundColor Cyan
    ollama pull all-minilm
    Write-Host "All Day 1 models ready!" -ForegroundColor Green
} else {
    Write-Host "Ollama was not detected on port 11434. Start Ollama from Start Menu and run this script again." -ForegroundColor Yellow
}
