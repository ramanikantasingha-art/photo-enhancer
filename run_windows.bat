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

echo Waiting for the backend and web interface...
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$front=$false; $back=$false; for($i=0;$i -lt 60;$i++){ try { $r=Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/' -TimeoutSec 1; if($r.StatusCode -eq 200){$back=$true} } catch {}; try { $r=Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:3000/' -TimeoutSec 1; if($r.StatusCode -eq 200){$front=$true} } catch {}; if($front -and $back){break}; Start-Sleep -Milliseconds 500 }; if($front -and $back){Start-Process 'http://127.0.0.1:3000'; exit 0}; Write-Host ('Backend ready: '+$back+', Frontend ready: '+$front) -ForegroundColor Red; exit 1"

if errorlevel 1 (
  echo.
  echo The complete app did not become ready within 30 seconds.
  echo Check the two Photo Enhancer windows for the exact error.
  pause
  exit /b 1
)
exit /b 0
