@echo off
setlocal
cd /d "%~dp0"
echo Starting Photo Enhancer setup...
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_windows.ps1"
set "SETUP_EXIT=%ERRORLEVEL%"

if "%SETUP_EXIT%"=="0" (
  echo.
  echo Installing Hybrid Engine V3 portrait matting...
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_modnet_model.ps1"
  set "SETUP_EXIT=%ERRORLEVEL%"
)

echo.
if not "%SETUP_EXIT%"=="0" (
  echo Setup did not finish. Read the red error above.
  echo You can take a screenshot of this window and send it to ChatGPT.
) else (
  echo Setup completed successfully.
  echo Hybrid Engine V3 with local MODNet portrait matting is ready.
  echo Double-click run_windows.bat to open the app.
)
echo.
pause
exit /b %SETUP_EXIT%
