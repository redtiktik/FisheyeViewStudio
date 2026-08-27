FISHEYE VIEW STUDIO - COMPACT PORTABLE BUILD
=============================================

Goal
----
Create dist\Fisheye-View-Studio-Windows-x64.zip below 100,000,000 bytes
while keeping the app fully portable on Windows 11 x64.

What changed
------------
1. Only ffmpeg.exe is bundled.
   ffprobe.exe is no longer needed because the app reads dimensions, duration,
   frame rate, codec, and audio information from ffmpeg.exe itself.

2. The build installs PySide6 Essentials instead of the full PySide6 Addons
   package. The app only needs Qt Core, GUI, and Widgets.

3. Unused Qt translation catalogs and optional image/network/style plugins are
   removed after PyInstaller creates the application folder.

4. The builder uses maximum standard ZIP/Deflate compression when 7-Zip is
   installed and otherwise uses Windows optimal ZIP compression.

5. The final verifier rejects any ZIP that is 100,000,000 bytes or larger.

Build steps
-----------
1. Run Setup-FFmpeg-Portable.bat.
2. Confirm tools\ffmpeg.exe exists.
3. Run Build-Portable-Under-100MB.bat.
4. Distribute only dist\Fisheye-View-Studio-Windows-x64.zip after the build
   reports COMPACT PORTABLE BUILD COMPLETED AND VERIFIED.

Optional
--------
Install 7-Zip before building for the strongest standard ZIP compression:
  winget install -e --id 7zip.7zip

The finished ZIP remains a normal ZIP archive and can be extracted without
installing Python or FFmpeg on the destination computer.
