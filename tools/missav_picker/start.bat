@echo off
setlocal EnableDelayedExpansion

cd /d "%~dp0"

set "PORT=8699"
set "PID_FILE=%~dp0.missav_picker.pid"
set "PYTHON_EXE=pythonw.exe"

if exist "%PID_FILE%" (
  set /p OLD_PID=<"%PID_FILE%"
  if defined OLD_PID (
    tasklist /FI "PID eq !OLD_PID!" 2>nul | findstr /R /C:"[ ]!OLD_PID![ ]" >nul
    if not errorlevel 1 (
      echo MissAV Picker is already running on http://localhost:%PORT% ^(PID !OLD_PID!^)
      start "" "http://localhost:%PORT%"
      exit /b 0
    )
  )
  del "%PID_FILE%" >nul 2>nul
)

where pythonw.exe >nul 2>nul
if errorlevel 1 set "PYTHON_EXE=python.exe"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$env:MISSAV_PICKER_PORT='%PORT%'; $p=Start-Process -FilePath '%PYTHON_EXE%' -ArgumentList 'server.py' -WorkingDirectory '%CD%' -WindowStyle Hidden -PassThru; Set-Content -LiteralPath '%PID_FILE%' -Value $p.Id"
if errorlevel 1 (
  echo Failed to start MissAV Picker. Make sure Python is installed and available in PATH.
  pause
  exit /b 1
)

echo MissAV Picker started on http://localhost:%PORT%
start "" "http://localhost:%PORT%"
