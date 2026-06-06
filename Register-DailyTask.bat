@echo off
chcp 65001 > nul
echo 正在向 Windows 系統註冊每日 19:05 自動分析與更新排程工作...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Register-DailyTask.ps1"
pause
