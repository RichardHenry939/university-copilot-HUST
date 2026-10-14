@echo off
REM (Claude 2026-10-02) Ghe "Local AI" — model chay tren may qua LM Studio (ghe phan bien cua hoi dong).
REM Cau hinh: <thư mục agentchattr>\config.local.toml [agents.local]
cd /d "%~dp0.."

REM LM Studio server (cong 1234) chua chay -> bat
powershell -NoProfile -Command "$c=New-Object Net.Sockets.TcpClient; try{$c.Connect('127.0.0.1',1234); exit 0}catch{exit 1}finally{$c.Close()}"
if errorlevel 1 (
    start "" /min "D:\AI\Cache\LMStudio\home\bin\lms.exe" server start
    timeout /t 8 /nobreak >nul
)

set PYTHONIOENCODING=utf-8
.venv\Scripts\python.exe wrapper_api.py local
if %errorlevel% neq 0 (
    echo.
    echo   Ghe Local AI thoat bat thuong. Xem thong bao phia tren.
    pause
)
