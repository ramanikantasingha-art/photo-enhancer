@echo off
setlocal
cd /d "%~dp0"
echo Starting Photo Enhancer setup...
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_windows.ps1"
set "SETUP_EXIT=%ERRORLEVEL%"
echo.
if not "%SETUP_EXIT%"=="0" (
  echo Setup did not finish. Read the red error above.
  echo You can take a screenshot of this window and send it to ChatGPT.
) else (
  echo Setup completed successfully.
  echo Double-click run_windows.bat to open the app.
)
echo.
pause
exit /b %SETUP_EXIT%
