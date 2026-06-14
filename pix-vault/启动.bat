@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo   PixVault — 本地图片画廊
echo   http://localhost:8720
echo.
echo   关闭此窗口即停止服务器
echo.
python run.py
pause
