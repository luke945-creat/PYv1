@echo off
chcp 65001 > nul
echo ==================================================
echo   Starting Attention and Disposition Dashboard...
echo ==================================================
echo.

echo 1. Cleaning up old server on Port 8001...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8001 ^| findstr LISTENING') do (
    taskkill /f /pid %%a > nul 2>&1
)

echo 2. Launching Python Web Server in the background...
powershell -Command "Start-Process python -ArgumentList '-m http.server 8001' -WindowStyle Hidden"

echo 3. Opening default browser to the dashboard...
ping 127.0.0.1 -n 2 > nul
start http://localhost:8001/index.html

echo 4. Dashboard started! This window will close automatically.
ping 127.0.0.1 -n 3 > nul
exit
