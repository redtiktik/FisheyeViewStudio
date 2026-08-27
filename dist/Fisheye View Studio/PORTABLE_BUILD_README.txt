FISHEYE VIEW STUDIO - COMPACT PORTABLE WINDOWS BUILD
====================================================

PURPOSE
-------

Create a self-contained Windows x64 ZIP that is smaller than 100,000,000
bytes. The package includes Python, the required PySide6/Qt components, and
FFmpeg. It intentionally omits ffprobe.exe and uses ffmpeg.exe itself to read
video metadata.

BUILD ORDER
-----------

1. Extract the source project into a normal local folder.

2. Run:

     Setup-FFmpeg-Portable.bat

   This locates or lets you select ffmpeg.exe, copies it and any required
   sibling DLLs into tools, and removes a stale ffprobe.exe from older builds.

3. Confirm this exists:

     tools\ffmpeg.exe

4. Run:

     Build-Portable-Under-100MB.bat

   The build uses a separate .venv-compact environment with
   PySide6-Essentials, runs the tests, packages the application, verifies
   bundled FFmpeg, creates the ZIP, and enforces the size limit.

5. Optional independent verification:

     Verify-Portable-Zip.bat

OUTPUT
------

  dist\Fisheye View Studio\
  dist\Fisheye-View-Studio-Windows-x64.zip

The destination computer does not need Python, FFmpeg, or ffprobe installed.
Extract the complete top-level folder before launching the application.

WHAT IS INCLUDED
----------------

  Fisheye View Studio.exe
  Python runtime
  PySide6 Essentials and required Qt files
  ffmpeg.exe
  Required FFmpeg DLLs, when applicable
  Assets, profiles, notices, and documentation

WHAT IS NOT INCLUDED
--------------------

  ffprobe.exe
  PySide6 Addons
  NVIDIA drivers
  User video files

SIZE CHECK
----------

The ZIP must be smaller than 100,000,000 bytes. The verifier rejects an
oversized archive and the builder prints the largest compiled files.

The builder uses 7-Zip maximum standard Deflate compression when 7-Zip is
installed. Otherwise, it uses Windows Compress-Archive.

IMPORTANT
---------

- Build the Windows package on Windows x64.
- Do not distribute only the EXE. Keep the complete application folder.
- NVIDIA NVENC is optional; CPU encoding remains available.
- Microsoft Defender SmartScreen may warn about an unsigned application.
