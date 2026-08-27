param(
    [Parameter(Position = 0)]
    [string]$ZipPath = (Join-Path $PSScriptRoot "dist\Fisheye-View-Studio-Windows-x64.zip"),

    [Parameter(Position = 1)]
    [Int64]$MaximumBytes = 100000000
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.IO.Compression.FileSystem

$ZipPath = [System.IO.Path]::GetFullPath($ZipPath)
if (-not (Test-Path -LiteralPath $ZipPath -PathType Leaf)) {
    throw "Portable ZIP not found: $ZipPath"
}

$zipFile = Get-Item -LiteralPath $ZipPath
$sizeMb = [Math]::Round($zipFile.Length / 1MB, 2)
$sizeDecimalMb = [Math]::Round($zipFile.Length / 1000000, 2)

Write-Host ""
Write-Host "Verifying compact portable ZIP:" -ForegroundColor Cyan
Write-Host "  $ZipPath"
Write-Host "  $($zipFile.Length) bytes ($sizeDecimalMb MB decimal / $sizeMb MiB)"
Write-Host ""

if ($zipFile.Length -ge $MaximumBytes) {
    throw "ZIP is not below the required limit of $MaximumBytes bytes."
}

$archive = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
try {
    $entryNames = @(
        $archive.Entries | ForEach-Object { $_.FullName -replace '\\', '/' }
    )

    $requiredPatterns = [ordered]@{
        "Application" = '(?i)(^|/)Fisheye View Studio\.exe$'
        "FFmpeg"      = '(?i)(^|/)tools/ffmpeg\.exe$'
    }

    foreach ($item in $requiredPatterns.GetEnumerator()) {
        $match = @($entryNames | Where-Object { $_ -match $item.Value })
        if ($match.Count -eq 0) {
            throw "$($item.Key) is missing from the ZIP."
        }
        Write-Host "[OK] $($item.Key) is present: $($match[0])"
    }

    if ($entryNames -match '(?i)(^|/)tools/ffprobe\.exe$') {
        throw "ffprobe.exe is present. The compact package should not bundle it."
    }
    Write-Host "[OK] ffprobe.exe is omitted"
}
finally {
    $archive.Dispose()
}

$tempRoot = Join-Path $env:TEMP ("FVS-Compact-Verify-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tempRoot | Out-Null

try {
    Expand-Archive -LiteralPath $ZipPath -DestinationPath $tempRoot -Force

    $app = Get-ChildItem -LiteralPath $tempRoot -Recurse -File |
        Where-Object { $_.Name -ieq "Fisheye View Studio.exe" } |
        Select-Object -First 1

    $ffmpeg = Get-ChildItem -LiteralPath $tempRoot -Recurse -File |
        Where-Object { $_.Name -ieq "ffmpeg.exe" } |
        Select-Object -First 1

    if (-not $app) { throw "Application executable was not found after extraction." }
    if (-not $ffmpeg) { throw "ffmpeg.exe was not found after extraction." }
    if ($app.Length -le 0) { throw "Application executable is empty after extraction." }
    if ($ffmpeg.Length -le 0) { throw "ffmpeg.exe is empty after extraction." }

    Write-Host ""
    Write-Host "Testing bundled FFmpeg:" -ForegroundColor Cyan
    $ffmpegVersion = @(& $ffmpeg.FullName -hide_banner -version 2>&1)
    if ($LASTEXITCODE -ne 0) { throw "Bundled ffmpeg.exe did not run successfully." }
    Write-Host ($ffmpegVersion | Select-Object -First 1)

    Write-Host ""
    Write-Host "PORTABLE PACKAGE VERIFIED SUCCESSFULLY" -ForegroundColor Green
    Write-Host "ZIP size is below 100,000,000 bytes."
    Write-Host "Python and a separate FFmpeg installation are not required."
}
finally {
    Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
