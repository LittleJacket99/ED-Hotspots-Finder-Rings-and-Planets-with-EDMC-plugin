@echo off
setlocal
cd /d "%~dp0"

set "VERSION=v1.0.5"
set "BUILD_EXE_NAME=ED Hotspots Finder - Rings & Planets.exe"
set "ASSET_EXE_NAME=ED-Hotspots-Finder-Rings-and-Planets-%VERSION%.exe"
set "RELEASE_DIR=%CD%\release\%VERSION%"
set "BUILD_WORK_DIR=%CD%\build-v1.0.5"
set "BUILD_DIST_DIR=%CD%\dist-v1.0.5"
set "DIST_EXE=%BUILD_DIST_DIR%\%BUILD_EXE_NAME%"
set "RELEASE_EXE=%RELEASE_DIR%\%ASSET_EXE_NAME%"
set "SHA_FILE=%RELEASE_DIR%\SHA256.txt"

echo =======================================================
echo ED Hotspots Finder - Rings ^& Planets %VERSION%
echo Windows release build
echo =======================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not available in the current environment.
    goto :fail
)

python -c "import json; from pathlib import Path; import hotspots_finder_gui_v8_final as app, finder_engine, local_scan, system_filter_search, community_deposits, results_export, rhinospotter_sync_service, requests, PIL; manifest=json.loads(Path('release_manifest.json').read_text(encoding='utf-8')); assert app.PUBLIC_APP_VERSION == 'v'+manifest['version'] == '%VERSION%', 'Release version mismatch'; print('Release imports OK')"
if errorlevel 1 goto :fail

for %%F in ("app.ico" "ED_Hotspots_Finder.png" "Mahon_logo.png" "version_info_v8.txt" "HotspotsFinder-v8.spec" "release_manifest.json") do (
    if not exist "%%~F" (
        echo ERROR: Required build file is missing: %%~F
        goto :fail
    )
)

python -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: PyInstaller is not installed in the current environment.
    echo Install it with: python -m pip install pyinstaller
    goto :fail
)

rem PyInstaller owns only these release work directories; do not delete old releases.

echo Building executable...
python -m PyInstaller --noconfirm --clean --workpath "%BUILD_WORK_DIR%" --distpath "%BUILD_DIST_DIR%" "HotspotsFinder-v8.spec"
if errorlevel 1 goto :fail

if not exist "%DIST_EXE%" (
    echo ERROR: Expected executable was not created.
    goto :fail
)

if not exist "%RELEASE_DIR%" mkdir "%RELEASE_DIR%"
if errorlevel 1 goto :fail

copy /y "%DIST_EXE%" "%RELEASE_EXE%" >nul
if errorlevel 1 goto :fail

echo Calculating SHA256 checksum...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $name=[IO.Path]::GetFileName($env:RELEASE_EXE); $sha=[Security.Cryptography.SHA256]::Create(); try{$hash=[BitConverter]::ToString($sha.ComputeHash([IO.File]::ReadAllBytes($env:RELEASE_EXE))).Replace('-','').ToLowerInvariant()}finally{$sha.Dispose()}; $lines=if(Test-Path -LiteralPath $env:SHA_FILE){Get-Content -LiteralPath $env:SHA_FILE | Where-Object {-not $_.EndsWith('  '+$name)}}else{@()}; @($lines)+($hash+'  '+$name) | Set-Content -LiteralPath $env:SHA_FILE -Encoding ASCII"
if errorlevel 1 goto :fail

if not exist "%SHA_FILE%" (
    echo ERROR: SHA256.txt was not created.
    goto :fail
)

echo.
echo =======================================================
echo RELEASE BUILD OK
echo =======================================================
echo EXE: "%RELEASE_EXE%"
echo SHA: "%SHA_FILE%"
echo.
echo Finder asset updated in the unified GitHub Release folder %VERSION%.
echo.
pause
exit /b 0

:fail
echo.
echo BUILD FAILED. Read the error above.
echo.
pause
exit /b 1
