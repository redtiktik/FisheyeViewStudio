@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if exist ".venv-compact\Scripts\python.exe" (
    ".venv-compact\Scripts\python.exe" -m unittest discover -s tests -v
    goto Done
)

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m unittest discover -s tests -v
    goto Done
)

where py.exe >nul 2>&1 && py -m unittest discover -s tests -v && goto Done
where python.exe >nul 2>&1 && python -m unittest discover -s tests -v && goto Done
echo Python was not found.

:Done
pause
