# Stop Project Golu PowerShell Script
Write-Host "Stopping Project Golu..." -ForegroundColor Yellow
Get-CimInstance Win32_Process | Where-Object { 
    $_.CommandLine -like "*start_golu.py*" -or $_.CommandLine -like "*mic_listener.py*" 
} | ForEach-Object { 
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue 
}
Write-Host "Project Golu stopped cleanly. All audio handles and VRAM released." -ForegroundColor Green
