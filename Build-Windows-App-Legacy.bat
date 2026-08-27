@echo off
echo This legacy build now redirects to the compact portable build.
call "%~dp0Build-Portable-With-FFmpeg.bat"
exit /b %ERRORLEVEL%
