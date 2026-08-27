@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo ============================================================
echo Fisheye View Studio - Install and Run
echo ============================================================
echo.

set "PYTHON_CMD="
where py.exe >nul 2>&1 && set "PYTHON_CMD=py"
if not defined PYTHON_CMD (
    where python.exe >nul 2>&1 && set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD (
    echo Python was not found.
    echo.
    echo Install Python 3.12 or newer, then run this file again.
    echo You can use:
    echo     winget install -e --id Python.Python.3.12
    echo.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating the local Python environment...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 goto Failed
)

call ".venv\Scripts\activate.bat"

echo Updating pip...
python -m pip install --upgrade pip
if errorlevel 1 goto Failed

echo Installing the application requirements...
python -m pip install -r requirements.txt
if errorlevel 1 goto Failed

echo.
echo Starting Fisheye View Studio...
start "" ".venv\Scripts\pythonw.exe" "%~dp0fisheye_view_studio.pyw"
exit /b 0

:Failed
echo.
echo Setup failed. Review the messages above.
echo.
pause
exit /b 1
