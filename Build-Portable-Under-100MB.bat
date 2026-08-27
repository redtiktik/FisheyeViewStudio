@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

rem ============================================================
rem Fisheye View Studio - Compact Portable Windows Build
rem
rem Goal: create a standard Windows ZIP below 100,000,000 bytes.
rem Main size reductions:
rem   - bundle ffmpeg.exe only; ffprobe.exe is no longer required
rem   - install PySide6 Essentials instead of the full Addons package
rem   - remove unused Qt translations and optional plugins
rem   - use maximum standard ZIP/Deflate compression when 7-Zip exists
rem ============================================================

set "APP_NAME=Fisheye View Studio"
set "APP_DIR=%CD%\dist\%APP_NAME%"
set "PORTABLE_ZIP=%CD%\dist\Fisheye-View-Studio-Windows-x64.zip"
set "VENV_DIR=%CD%\.venv-compact"
set "MAX_ZIP_BYTES=100000000"

if not exist "tools\ffmpeg.exe" goto MissingFFmpeg

rem Never allow a stale ffprobe.exe to be packaged.
if exist "tools\ffprobe.exe" del /q "tools\ffprobe.exe"

"tools\ffmpeg.exe" -hide_banner -version >nul 2>&1
if errorlevel 1 goto InvalidBundledTool

echo.
echo ============================================================
echo Fisheye View Studio - Compact Portable Build
 echo ============================================================
echo.
echo Bundled FFmpeg found and validated.
echo ffprobe.exe will not be included.
echo.

set "PYTHON_CMD="
where py.exe >nul 2>&1 && set "PYTHON_CMD=py"
if not defined PYTHON_CMD (
    where python.exe >nul 2>&1 && set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD (
    echo ERROR: Python was not found.
    echo Install Python 3.11 or newer, then run this file again.
    echo.
    echo Suggested command:
    echo   winget install -e --id Python.Python.3.12
    echo.
    pause
    exit /b 1
)

if not exist "%VENV_DIR%\Scripts\python.exe" (
    %PYTHON_CMD% -m venv "%VENV_DIR%"
    if errorlevel 1 goto Failed
)

call "%VENV_DIR%\Scripts\activate.bat"
python -m pip install --upgrade pip
if errorlevel 1 goto Failed

python -m pip install -r requirements-build.txt
if errorlevel 1 goto Failed

rem Confirm the compact environment did not install PySide6 Addons.
python -m pip show PySide6-Addons >nul 2>&1
if not errorlevel 1 (
    echo.
    echo WARNING: PySide6 Addons exists in the compact environment.
    echo Recreating the compact environment to ensure an Essentials-only build...
    call deactivate >nul 2>&1
    rmdir /s /q "%VENV_DIR%"
    %PYTHON_CMD% -m venv "%VENV_DIR%"
    if errorlevel 1 goto Failed
    call "%VENV_DIR%\Scripts\activate.bat"
    python -m pip install --upgrade pip
    if errorlevel 1 goto Failed
    python -m pip install -r requirements-build.txt
    if errorlevel 1 goto Failed
)

echo Running core tests...
python -m unittest discover -s tests -v
if errorlevel 1 goto Failed

rem Remove old output so stale binaries cannot pass verification.
if exist build rmdir /s /q build
if exist "%APP_DIR%" rmdir /s /q "%APP_DIR%"
if exist "%PORTABLE_ZIP%" del /q "%PORTABLE_ZIP%"

python -m PyInstaller --noconfirm --clean FisheyeViewStudio.spec
if errorlevel 1 goto Failed

if not exist "%APP_DIR%\%APP_NAME%.exe" (
    echo.
    echo ERROR: The compiled application executable was not created.
    goto Failed
)

rem Remove optional Qt content the application does not use.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%CD%\Trim-Portable-Runtime.ps1" -ApplicationFolder "%APP_DIR%"
if errorlevel 1 goto Failed

copy /y README.md "%APP_DIR%\README.md" >nul
if exist START_HERE.txt copy /y START_HERE.txt "%APP_DIR%\START_HERE.txt" >nul
if exist PORTABLE_BUILD_README.txt copy /y PORTABLE_BUILD_README.txt "%APP_DIR%\PORTABLE_BUILD_README.txt" >nul
if exist PRIVACY_AND_BRANDING.txt copy /y PRIVACY_AND_BRANDING.txt "%APP_DIR%\PRIVACY_AND_BRANDING.txt" >nul
if exist COMPACT_BUILD_README.txt copy /y COMPACT_BUILD_README.txt "%APP_DIR%\COMPACT_BUILD_README.txt" >nul
if exist profiles xcopy /e /i /y profiles "%APP_DIR%\profiles" >nul

set "COMPILED_FFMPEG="
for /f "delims=" %%F in ('dir /s /b "%APP_DIR%\ffmpeg.exe" 2^>nul') do (
    if not defined COMPILED_FFMPEG set "COMPILED_FFMPEG=%%~fF"
)

if not defined COMPILED_FFMPEG goto MissingFromBuild

"%COMPILED_FFMPEG%" -hide_banner -version >nul 2>&1
if errorlevel 1 goto BrokenCompiledFFmpeg

rem Make certain no ffprobe copy slipped into the output.
for /f "delims=" %%F in ('dir /s /b "%APP_DIR%\ffprobe.exe" 2^>nul') do del /q "%%~fF"

(
    echo Fisheye View Studio Compact Portable Package
    echo =============================================
    echo.
    echo Build date: %DATE% %TIME%
    echo Architecture: Windows x64
    echo ZIP limit: less than 100,000,000 bytes
    echo.
    echo Application:
    echo   %APP_NAME%.exe
    echo.
    echo Bundled FFmpeg:
    echo   !COMPILED_FFMPEG:%APP_DIR%\=!
    echo.
    echo ffprobe.exe is not bundled. The application reads media information
    echo through ffmpeg.exe itself.
    echo.
    echo Python and PySide6/Qt are bundled by PyInstaller.
    echo Python and FFmpeg do not need to be installed on the destination PC.
) > "%APP_DIR%\PORTABLE_PACKAGE_INFO.txt"

rem Prefer 7-Zip's strongest normal Deflate ZIP settings when installed.
set "SEVENZIP="
for /f "delims=" %%F in ('where.exe 7z.exe 2^>nul') do if not defined SEVENZIP set "SEVENZIP=%%~fF"
if exist "%ProgramFiles%\7-Zip\7z.exe" set "SEVENZIP=%ProgramFiles%\7-Zip\7z.exe"
if not defined SEVENZIP if exist "%ProgramFiles(x86)%\7-Zip\7z.exe" set "SEVENZIP=%ProgramFiles(x86)%\7-Zip\7z.exe"

if defined SEVENZIP (
    echo Creating ZIP with maximum standard Deflate compression...
    pushd "%CD%\dist"
    "%SEVENZIP%" a -tzip -mx=9 -mm=Deflate -mfb=258 -mpass=15 "%PORTABLE_ZIP%" "%APP_NAME%" >nul
    set "ZIP_RESULT=!ERRORLEVEL!"
    popd
    if not "!ZIP_RESULT!"=="0" goto Failed
) else (
    echo 7-Zip was not found. Using Windows optimal ZIP compression...
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
      "$ErrorActionPreference='Stop'; $source=$env:APP_DIR; $zip=$env:PORTABLE_ZIP; if(Test-Path -LiteralPath $zip){Remove-Item -LiteralPath $zip -Force}; Compress-Archive -LiteralPath $source -DestinationPath $zip -CompressionLevel Optimal"
    if errorlevel 1 goto Failed
)

if not exist "%PORTABLE_ZIP%" goto Failed

for %%Z in ("%PORTABLE_ZIP%") do set "ZIP_BYTES=%%~zZ"
set /a ZIP_MB_DECIMAL=!ZIP_BYTES!/1000000

echo.
echo ZIP size: !ZIP_BYTES! bytes - approximately !ZIP_MB_DECIMAL! MB decimal

if !ZIP_BYTES! GEQ %MAX_ZIP_BYTES% goto ZipTooLarge

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%CD%\Verify-Portable-Zip.ps1" "%PORTABLE_ZIP%" %MAX_ZIP_BYTES%
if errorlevel 1 goto ZipVerificationFailed

echo.
echo ============================================================
echo COMPACT PORTABLE BUILD COMPLETED AND VERIFIED
 echo ============================================================
echo.
echo Portable ZIP:
echo   "%PORTABLE_ZIP%"
echo.
echo Final size:
echo   !ZIP_BYTES! bytes - below 100 MB
 echo.
echo Included:
echo   Fisheye View Studio.exe
 echo   ffmpeg.exe
 echo   Python and PySide6/Qt runtime
 echo.
echo Not included:
echo   ffprobe.exe
 echo   PySide6 Addons
 echo   unused Qt translations/plugins
 echo.
start "" "%CD%\dist"
pause
exit /b 0

:MissingFFmpeg
echo.
echo ERROR: tools\ffmpeg.exe is missing.
echo Run Setup-FFmpeg-Portable.bat first.
echo.
pause
exit /b 1

:InvalidBundledTool
echo.
echo ERROR: tools\ffmpeg.exe does not run correctly.
echo Run Setup-FFmpeg-Portable.bat again.
echo.
pause
exit /b 1

:MissingFromBuild
echo.
echo ERROR: PyInstaller completed, but ffmpeg.exe was not found in the app folder.
echo.
pause
exit /b 1

:BrokenCompiledFFmpeg
echo.
echo ERROR: Bundled FFmpeg could not run from the compiled app folder.
echo If you selected a shared build, required DLL files may be missing.
echo.
pause
exit /b 1

:ZipTooLarge
echo.
echo ============================================================
echo ERROR: ZIP IS STILL TOO LARGE
 echo ============================================================
echo.
echo Size: !ZIP_BYTES! bytes
 echo Limit: less than %MAX_ZIP_BYTES% bytes
 echo.
echo Use a static FFmpeg essentials build, then rerun:
echo   Setup-FFmpeg-Portable.bat
 echo   Build-Portable-Under-100MB.bat
 echo.
echo The oversized ZIP was left in dist for inspection but should not be distributed.
echo.
echo Largest files in the compiled application:
powershell.exe -NoProfile -Command "Get-ChildItem -LiteralPath $env:APP_DIR -Recurse -File ^| Sort-Object Length -Descending ^| Select-Object -First 12 @{N='MB';E={[math]::Round($_.Length/1MB,2)}}, FullName ^| Format-Table -AutoSize"
echo.
pause
exit /b 1

:ZipVerificationFailed
echo.
echo ERROR: The ZIP was created, but final verification failed.
echo Do not distribute it until the error above is corrected.
echo.
pause
exit /b 1

:Failed
echo.
echo ERROR: The compact build failed. Review the messages above.
echo.
pause
exit /b 1
