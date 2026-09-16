@echo off
echo Stopping Photo Enhancer...
taskkill /FI "WINDOWTITLE eq Photo Enhancer Backend*" /T /F >nul 2>nul
taskkill /FI "WINDOWTITLE eq Photo Enhancer Frontend*" /T /F >nul 2>nul
echo Photo Enhancer stopped.
timeout /t 2 /nobreak >nul
