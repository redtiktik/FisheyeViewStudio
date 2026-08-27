@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not exist "dist\Fisheye View Studio\Fisheye View Studio.exe" (
    echo The application has not been built yet.
    echo Run Build-Windows-App.bat first.
    pause
    exit /b 1
)

set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if not defined ISCC (
    echo Inno Setup 6 was not found.
    echo Install it and run this file again.
    echo.
    echo     winget install -e --id JRSoftware.InnoSetup
    echo.
    pause
    exit /b 1
)

"%ISCC%" "installer\FisheyeViewStudio.iss"
if errorlevel 1 (
    echo Installer build failed.
    pause
    exit /b 1
)

echo.
echo Installer created in:
echo "%~dp0dist\installer"
echo.
start "" "%~dp0dist\installer"
pause
