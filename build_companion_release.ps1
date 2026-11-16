param(
    [string]$Version
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PluginSource = Join-Path $RepoRoot "edmc_plugin\EDHF_Community_Navigator"
$LoadPy = Join-Path $PluginSource "load.py"
$Manifest = Get-Content -LiteralPath (Join-Path $RepoRoot "release_manifest.json") -Raw | ConvertFrom-Json

if (-not (Test-Path $LoadPy)) {
    throw "Companion load.py not found: $LoadPy"
}

if (-not $Version) {
    $match = Select-String -Path $LoadPy -Pattern '^VERSION\s*=\s*"([^"]+)"$' | Select-Object -First 1
    if (-not $match) {
        throw "Could not read VERSION from $LoadPy"
    }

    $Version = $match.Matches[0].Groups[1].Value
}

$SourceVersionMatch = Select-String -LiteralPath $LoadPy -Pattern '^VERSION\s*=\s*"([^"]+)"$' | Select-Object -First 1
if (-not $SourceVersionMatch -or $SourceVersionMatch.Matches[0].Groups[1].Value -ne $Manifest.version -or $Version -ne $Manifest.version) {
    throw "Plugin, release manifest and requested version must match."
}
if ($Version -ne "1.0.5") {
    throw "This packaging configuration is reserved for 1.0.5."
}
foreach ($Name in $Manifest.plugin_sources) {
    if ([IO.Path]::GetFileName($Name) -ne $Name -or -not (Test-Path -LiteralPath (Join-Path $PluginSource $Name) -PathType Leaf)) {
        throw "Invalid or missing plugin source: $Name"
    }
}

$ReleaseDir = Join-Path $RepoRoot "release\v$Version"
$StageRoot = Join-Path ([IO.Path]::GetTempPath()) ("Hotspots-Finder-EDMC-Plugin-$Version-" + [guid]::NewGuid().ToString("N"))
$StagePlugin = Join-Path $StageRoot "EDHF_Community_Navigator"
$ZipPath = Join-Path $ReleaseDir "Hotspots-Finder-EDMC-Plugin-v$Version.zip"
$HashPath = Join-Path $ReleaseDir "SHA256.txt"

New-Item -ItemType Directory -Path $StagePlugin -Force | Out-Null
New-Item -ItemType Directory -Path $ReleaseDir -Force | Out-Null

foreach ($Name in @($Manifest.plugin_sources) + @("README.md")) {
    Copy-Item -LiteralPath (Join-Path $PluginSource $Name) -Destination $StagePlugin
}
Copy-Item -LiteralPath (Join-Path $RepoRoot "LICENSE") -Destination $StagePlugin

Compress-Archive -Path $StagePlugin -DestinationPath $ZipPath -CompressionLevel Optimal -Force

$name = [System.IO.Path]::GetFileName($ZipPath)
$lines = @()
if (Test-Path $HashPath) {
    $lines = @(
        Get-Content $HashPath |
            Where-Object { $_ -notmatch ("  " + [regex]::Escape($name) + "$") }
    )
}
$sha = [Security.Cryptography.SHA256]::Create()
try {
    $hash = [BitConverter]::ToString($sha.ComputeHash([IO.File]::ReadAllBytes($ZipPath))).Replace('-', '').ToLowerInvariant()
} finally {
    $sha.Dispose()
}
$lines += "$hash  $name"
$lines | Set-Content -Path $HashPath -Encoding ascii

$ResolvedStage = [IO.Path]::GetFullPath($StageRoot)
$ExpectedStageParent = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
if (-not $ResolvedStage.StartsWith($ExpectedStageParent, [StringComparison]::OrdinalIgnoreCase) -or
    [IO.Path]::GetFileName($ResolvedStage) -notlike "Hotspots-Finder-EDMC-Plugin-1.0.5-*") {
    throw "Unexpected package staging path; cleanup refused."
}
Remove-Item -LiteralPath $ResolvedStage -Recurse -Force

Write-Host ""
Write-Host "Hotspots Finder EDMC Plugin v$Version"
Write-Host "ZIP:    $ZipPath"
Write-Host "SHA256: $HashPath"
Write-Host ""
Write-Host "The ZIP contains the EDHF_Community_Navigator folder ready to copy into:"
Write-Host "%LOCALAPPDATA%\EDMarketConnector\plugins\"
