param(
    [Parameter(Mandatory = $true)]
    [string]$ApplicationFolder
)

$ErrorActionPreference = "Stop"
$ApplicationFolder = [System.IO.Path]::GetFullPath($ApplicationFolder)
if (-not (Test-Path -LiteralPath $ApplicationFolder -PathType Container)) {
    throw "Application folder not found: $ApplicationFolder"
}

$removedBytes = [int64]0
$removedItems = New-Object System.Collections.Generic.List[string]

function Remove-CompactItem {
    param([Parameter(Mandatory = $true)][System.IO.FileSystemInfo]$Item)

    if ($Item.PSIsContainer) {
        $size = (Get-ChildItem -LiteralPath $Item.FullName -Recurse -File -ErrorAction SilentlyContinue |
            Measure-Object -Property Length -Sum).Sum
    }
    else {
        $size = $Item.Length
    }

    if (-not $size) { $size = 0 }
    $script:removedBytes += [int64]$size
    $script:removedItems.Add($Item.FullName.Substring($ApplicationFolder.Length).TrimStart('\'))
    Remove-Item -LiteralPath $Item.FullName -Recurse -Force -ErrorAction Stop
}

# English text is built into Qt. Translation catalogs are not needed by this
# English-only application and are safe to omit from a portable package.
Get-ChildItem -LiteralPath $ApplicationFolder -Recurse -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -ieq "translations" } |
    Sort-Object FullName -Descending |
    ForEach-Object { Remove-CompactItem $_ }

# The app reads only PNG frame previews and an ICO application icon. Qt's PNG
# support is built in; keep qico.dll and remove unused optional image handlers.
$unusedPluginFiles = @(
    "qgif.dll",
    "qicns.dll",
    "qjpeg.dll",
    "qsvg.dll",
    "qtga.dll",
    "qtiff.dll",
    "qwbmp.dll",
    "qwebp.dll",
    "qsvgicon.dll"
)

Get-ChildItem -LiteralPath $ApplicationFolder -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $unusedPluginFiles -contains $_.Name.ToLowerInvariant() } |
    ForEach-Object { Remove-CompactItem $_ }

# The UI explicitly uses Qt's built-in Fusion style. External style plugins are
# unnecessary. Network/TLS Qt plugins are also unused; FFmpeg and Python handle
# the application's work without Qt networking.
$unusedPluginDirectories = @("styles", "generic", "networkinformation", "tls")
Get-ChildItem -LiteralPath $ApplicationFolder -Recurse -Directory -ErrorAction SilentlyContinue |
    Where-Object { $unusedPluginDirectories -contains $_.Name.ToLowerInvariant() } |
    Sort-Object FullName -Descending |
    ForEach-Object { Remove-CompactItem $_ }

Write-Host "Runtime trim removed $($removedItems.Count) item(s), $removedBytes bytes." -ForegroundColor Cyan
foreach ($item in $removedItems) {
    Write-Host "  - $item"
}
