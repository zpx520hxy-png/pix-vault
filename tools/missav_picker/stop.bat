@echo off
setlocal EnableDelayedExpansion

cd /d "%~dp0"

set "PORT=8699"
set "PID_FILE=%~dp0.missav_picker.pid"
set "STOPPED="

if exist "%PID_FILE%" (
  set /p PID=<"%PID_FILE%"
  if defined PID (
    tasklist /FI "PID eq !PID!" 2>nul | findstr /R /C:"[ ]!PID![ ]" >nul
    if not errorlevel 1 (
      echo Stopping MissAV Picker PID !PID!...
      taskkill /PID !PID! /T /F >nul 2>nul
      set "STOPPED=1"
    )
  )
  del "%PID_FILE%" >nul 2>nul
)

for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%PORT% .*LISTENING"') do (
  echo Stopping process on port %PORT% ^(PID %%P^)...
  taskkill /PID %%P /T /F >nul 2>nul
  set "STOPPED=1"
)

if defined STOPPED (
  echo MissAV Picker stopped.
) else (
  echo MissAV Picker is not running on port %PORT%.
)
