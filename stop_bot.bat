@echo off
chcp 65001 > nul
echo Telegram Bot to'xtatilmoqda...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python' -and $_.CommandLine -match 'bot\.py' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host ('To''xtatildi PID: ' + $_.ProcessId) }"
echo Bot to'xtatildi!
timeout /t 2 > nul
