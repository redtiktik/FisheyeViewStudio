@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

rem ============================================================
rem Fisheye View Studio - Compact Portable FFmpeg Setup
rem
rem The compact package intentionally bundles ffmpeg.exe only.
rem The application now reads media information through ffmpeg.exe,
rem so ffprobe.exe is not required in the portable ZIP.
rem ============================================================

set "TOOLS_DIR=%CD%\tools"
if not exist "%TOOLS_DIR%" mkdir "%TOOLS_DIR%"

set "FFMPEG_SOURCE="

rem Accept ffmpeg.exe as the first command-line argument.
if not "%~1"=="" (
    if exist "%~1" set "FFMPEG_SOURCE=%~f1"
)

rem Search Windows PATH.
if not defined FFMPEG_SOURCE (
    for /f "delims=" %%F in ('where.exe ffmpeg.exe 2^>nul') do (
        if not defined FFMPEG_SOURCE set "FFMPEG_SOURCE=%%~fF"
    )
)

rem Search the known FFmpeg paths used by this project.
if not defined FFMPEG_SOURCE if exist "C:\FFmpeg\ffmpeg-7.1.1-essentials_build\bin\ffmpeg.exe" set "FFMPEG_SOURCE=C:\FFmpeg\ffmpeg-7.1.1-essentials_build\bin\ffmpeg.exe"
if not defined FFMPEG_SOURCE if exist "C:\FFmpeg\bin\ffmpeg.exe" set "FFMPEG_SOURCE=C:\FFmpeg\bin\ffmpeg.exe"

rem Let the user browse when automatic detection fails.
if not defined FFMPEG_SOURCE (
    echo.
    echo FFmpeg was not found automatically. Select ffmpeg.exe in the window that opens.
    echo.
    for /f "usebackq delims=" %%F in (`powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -Command ^
        "Add-Type -AssemblyName System.Windows.Forms; $d=New-Object System.Windows.Forms.OpenFileDialog; $d.Title='Select ffmpeg.exe'; $d.Filter='FFmpeg executable (ffmpeg.exe)|ffmpeg.exe|Executable files (*.exe)|*.exe'; if($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK){$d.FileName}"`) do (
        if not defined FFMPEG_SOURCE set "FFMPEG_SOURCE=%%~fF"
    )
)

if not defined FFMPEG_SOURCE goto NotFound
if not exist "%FFMPEG_SOURCE%" goto NotFound

"%FFMPEG_SOURCE%" -hide_banner -version >nul 2>&1
if errorlevel 1 goto InvalidFFmpeg

for %%F in ("%FFMPEG_SOURCE%") do set "SOURCE_DIR=%%~dpF"

rem Remove stale copies. ffprobe.exe is deliberately excluded.
del /q "%TOOLS_DIR%\ffmpeg.exe" 2>nul
del /q "%TOOLS_DIR%\ffprobe.exe" 2>nul
del /q "%TOOLS_DIR%\*.dll" 2>nul

copy /y "%FFMPEG_SOURCE%" "%TOOLS_DIR%\ffmpeg.exe" >nul
if errorlevel 1 goto CopyFailed

rem Shared FFmpeg builds need DLL files from the same bin directory.
rem A static/essentials build is preferred because it normally stays smaller.
set "DLL_COUNT=0"
for %%D in ("!SOURCE_DIR!*.dll") do (
    if exist "%%~fD" (
        copy /y "%%~fD" "%TOOLS_DIR%\%%~nxD" >nul
        set /a DLL_COUNT+=1
    )
)

"%TOOLS_DIR%\ffmpeg.exe" -hide_banner -version > "%TOOLS_DIR%\FFMPEG_BUILD_INFO.txt" 2>&1
if errorlevel 1 goto CopyFailed

rem Include any license/readme files found beside the selected build.
set "LICENSE_DIR=%TOOLS_DIR%\licenses\FFmpeg"
if exist "%LICENSE_DIR%" rmdir /s /q "%LICENSE_DIR%"
mkdir "%LICENSE_DIR%" >nul 2>&1

for %%R in ("!SOURCE_DIR!..") do set "SOURCE_ROOT=%%~fR"
for %%L in (LICENSE LICENSE.txt COPYING COPYING.GPLv2 COPYING.GPLv3 COPYING.LGPLv2.1 COPYING.LGPLv3 README README.txt README.md) do (
    if exist "!SOURCE_ROOT!\%%L" copy /y "!SOURCE_ROOT!\%%L" "%LICENSE_DIR%\%%L" >nul
)

(
    echo FFmpeg Third-Party Notice
    echo =========================
    echo.
    echo This portable package contains an FFmpeg binary obtained from the
    echo FFmpeg installation selected when Setup-FFmpeg-Portable.bat was run.
    echo.
    echo Project information and source code:
    echo https://ffmpeg.org/
    echo.
    echo The exact build configuration is recorded in FFMPEG_BUILD_INFO.txt.
    echo Any license files located with the selected build were copied into
    echo tools\licenses\FFmpeg.
    echo.
    echo ffprobe.exe is intentionally not bundled. The application uses
    echo ffmpeg.exe itself to read media information.
) > "%TOOLS_DIR%\THIRD_PARTY_NOTICES.txt"

"%TOOLS_DIR%\ffmpeg.exe" -hide_banner -version >nul 2>&1
if errorlevel 1 goto CopyFailed

for %%F in ("%TOOLS_DIR%\ffmpeg.exe") do set "FFMPEG_BYTES=%%~zF"

echo.
echo ============================================================
echo Compact FFmpeg setup completed.
echo ============================================================
echo.
echo Copied:
echo   "%TOOLS_DIR%\ffmpeg.exe"
echo.
echo Not bundled:
echo   ffprobe.exe

echo FFmpeg size: !FFMPEG_BYTES! bytes
if !DLL_COUNT! GTR 0 (
    echo.
    echo WARNING: !DLL_COUNT! shared FFmpeg DLL file(s) were also copied.
    echo A static essentials build is more likely to keep the final ZIP under 100 MB.
)
echo.
echo Next, run:
echo   Build-Portable-Under-100MB.bat
echo.
pause
exit /b 0

:NotFound
echo.
echo ERROR: ffmpeg.exe was not selected or could not be found.
echo.
echo Install FFmpeg or run this file with the full path:
echo   Setup-FFmpeg-Portable.bat "C:\path\to\ffmpeg.exe"
echo.
pause
exit /b 1

:InvalidFFmpeg
echo.
echo ERROR: The selected ffmpeg.exe could not be executed:
echo   "%FFMPEG_SOURCE%"
echo.
pause
exit /b 1

:CopyFailed
echo.
echo ERROR: FFmpeg could not be copied or validated in:
echo   "%TOOLS_DIR%"
echo.
pause
exit /b 1
