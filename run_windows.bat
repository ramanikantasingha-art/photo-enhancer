@echo off
setlocal
cd /d "%~dp0"

if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Photo Enhancer is not installed yet.
  echo First double-click setup_windows.bat and wait for SETUP COMPLETE.
  echo.
  pause
  exit /b 1
)

where npm.cmd >nul 2>nul
if errorlevel 1 (
  echo Node.js/npm is missing. Please reinstall Node.js LTS.
  echo.
  pause
  exit /b 1
)

echo Starting Photo Enhancer...
start "Photo Enhancer Backend" /D "%~dp0backend" cmd.exe /k ""%~dp0.venv\Scripts\python.exe" -m uvicorn app:app --host 127.0.0.1 --port 8000"
start "Photo Enhancer Frontend" /D "%~dp0frontend" cmd.exe /k "npm.cmd run dev -- --host 127.0.0.1"

echo Waiting for the app to become ready...
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$ok=$false; for($i=0;$i -lt 40;$i++){ try { $r=Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:3000' -TimeoutSec 1; if($r.StatusCode -eq 200){$ok=$true; break} } catch {}; Start-Sleep -Milliseconds 500 }; if($ok){Start-Process 'http://127.0.0.1:3000'; exit 0}else{exit 1}"

if errorlevel 1 (
  echo.
  echo The app did not open within 20 seconds.
  echo Check the two Photo Enhancer windows for the exact error.
  pause
  exit /b 1
)
exit /b 0
