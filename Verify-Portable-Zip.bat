@echo off
setlocal EnableExtensions
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%CD%\Verify-Portable-Zip.ps1" "%CD%\dist\Fisheye-View-Studio-Windows-x64.zip" 100000000
set "RESULT=%ERRORLEVEL%"
echo.
if not "%RESULT%"=="0" echo Portable ZIP verification failed.
pause
exit /b %RESULT%
