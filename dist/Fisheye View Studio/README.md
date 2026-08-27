# Fisheye View Studio

A local Windows 11 application for converting circular fisheye footage into normal 1920×1080 perspective videos with FFmpeg.

## Features

- Select or drag in common video files.
- Display a source frame with draggable view markers.
- Change FFmpeg roll, pitch, horizontal FOV, and vertical FOV visually.
- Generate real first-frame dewarped previews.
- Preserve the original running timestamp by cropping and overlaying its source strip.
- Render enabled views at 1920×1080 and 3 Mbps by default.
- Use NVIDIA NVENC when available and CPU `libx264` otherwise.
- Save and load reusable JSON camera layouts.
- Run short test renders before processing long recordings.

The source boxes are aiming guides. The generated FFmpeg preview is the authoritative view.

## Compact portable edition

This edition is designed to keep the final Windows ZIP below **100,000,000 bytes** while remaining self-contained.

It reduces package size in three ways:

1. Installs `PySide6-Essentials` rather than the full PySide6 package with Addons.
2. Bundles `ffmpeg.exe` but not the separate `ffprobe.exe` executable.
3. Uses maximum standard ZIP compression through 7-Zip when 7-Zip is installed on the build computer.

The application still reads video dimensions, duration, frame rate, codec, and audio presence. When `ffprobe.exe` is unavailable, it parses those details from `ffmpeg.exe` itself. If a user manually selects an FFmpeg folder that also contains ffprobe, the structured ffprobe method is used automatically.

The compact package still includes:

```text
Fisheye View Studio.exe
Python runtime
PySide6 Essentials and required Qt files
ffmpeg.exe
Required FFmpeg DLLs, when the selected build uses them
Application assets and example profiles
```

A separate Python or FFmpeg installation is not required on the destination computer.

## Build the compact portable ZIP

### Requirements on the build computer

- Windows 11 x64
- Python 3.11 or newer
- A working `ffmpeg.exe`
- Optional: 7-Zip for the smallest standard ZIP

### Steps

1. Run:

```text
Setup-FFmpeg-Portable.bat
```

2. Run:

```text
Build-Portable-Under-100MB.bat
```

The finished files are created under:

```text
dist\Fisheye View Studio\
dist\Fisheye-View-Studio-Windows-x64.zip
```

The build script automatically:

- Uses a separate `.venv-compact` environment.
- Installs PySide6 Essentials and PyInstaller.
- Refuses to package PySide6 Addons.
- Runs the core test suite.
- Packages only FFmpeg, not ffprobe.
- Verifies the bundled FFmpeg executable after extraction.
- Rejects a ZIP that is 100,000,000 bytes or larger.
- Prints the largest compiled files if the size check fails.

The existing `Build-Windows-App.bat` also redirects to the compact builder.

## Run from source

Run:

```text
Install-and-Run.bat
```

The source version uses `requirements.txt`, which installs PySide6 Essentials. Only `ffmpeg.exe` is required. `ffprobe.exe` is optional.

## Application workflow

1. Open Fisheye View Studio.
2. Select or drag in a fisheye video.
3. Wait for the source frame and previews.
4. Drag view markers around the circular image.
5. Adjust roll, pitch, horizontal FOV, or vertical FOV as needed.
6. Enable only the outputs that should be rendered.
7. Confirm the yellow timestamp crop covers the original timestamp label.
8. Leave output quality at 1920×1080 and 3000 kbps unless another setting is needed.
9. Run a short test render for long recordings.
10. Render the final views.

## Default output settings

```text
Resolution: 1920×1080
Video codec: H.264
Target video bitrate: 3000 kbps
Maximum video bitrate: approximately 5000 kbps
Audio: AAC 128 kbps when present
Interpolation: cubic
```

## Angle mapping

```text
Top of circle:    roll 0
Right side:       roll 90
Bottom:           roll 180
Left side:        roll -90
Distance outward: controls pitch
```

## FFmpeg discovery

The application searches for FFmpeg in this order:

1. Bundled `tools\ffmpeg.exe`
2. `ffmpeg.exe` beside the application
3. `C:\FFmpeg\ffmpeg-7.1.1-essentials_build\bin\ffmpeg.exe`
4. `C:\FFmpeg\bin\ffmpeg.exe`
5. Windows PATH

You can also select `ffmpeg.exe` manually in the application.

## Troubleshooting

### ZIP is still over 100 MB

The builder will stop and list the largest files. Confirm:

- `ffprobe.exe` is not present in the compiled package.
- The build used `.venv-compact`, not an older full PySide6 environment.
- `requirements.txt` contains `PySide6-Essentials`.
- 7-Zip is installed if additional compression is needed.
- The selected FFmpeg build does not include unusually large dependency DLLs.

### FFmpeg not found

Run `Setup-FFmpeg-Portable.bat` again or choose `ffmpeg.exe` inside the application.

### NVIDIA NVENC unavailable

The app falls back to CPU encoding. Confirm the selected FFmpeg build exposes `h264_nvenc` and that the computer has compatible NVIDIA drivers.

### Timestamp is cut off

Increase the timestamp crop width or height in advanced settings.

## Privacy

The current application processes files locally. It does not upload videos, frames, profiles, or logs to an external service.
