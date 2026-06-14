@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo   PixVault [测试环境] — 本地图片画廊
echo   http://localhost:8721
echo.
echo   关闭此窗口即停止服务器
echo.
python run_test.py
pause
