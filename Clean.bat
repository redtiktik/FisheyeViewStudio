@echo off
cd /d "%~dp0"
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist __pycache__ rmdir /s /q __pycache__
for /d /r %%D in (__pycache__) do @if exist "%%D" rmdir /s /q "%%D"
echo Build files removed.
pause
