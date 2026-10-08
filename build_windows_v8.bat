@echo off
setlocal
cd /d "%~dp0"

set "VERSION=v1.0.3"
set "BUILD_EXE_NAME=ED Hotspots Finder - Rings & Planets.exe"
set "ASSET_EXE_NAME=ED-Hotspots-Finder-Rings-and-Planets-%VERSION%.exe"
set "RELEASE_DIR=%CD%\release\%VERSION%"
set "DIST_EXE=%CD%\dist-v8\%BUILD_EXE_NAME%"
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

python -c "import hotspots_finder_gui_v8_final, finder_engine, local_scan, system_filter_search, community_deposits, results_export, rhinospotter_sync_service, requests; print('Release imports OK')"
if errorlevel 1 goto :fail

for %%F in ("app.ico" "ED_Hotspots_Finder.png" "version_info_v8.txt" "HotspotsFinder-v8.spec") do (
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

if exist "build-v8" rmdir /s /q "build-v8"
if exist "dist-v8" rmdir /s /q "dist-v8"

echo Building executable...
python -m PyInstaller --noconfirm --clean --workpath "build-v8" --distpath "dist-v8" "HotspotsFinder-v8.spec"
if errorlevel 1 goto :fail

if not exist "%DIST_EXE%" (
    echo ERROR: Expected executable was not created.
    goto :fail
)

if not exist "%RELEASE_DIR%" mkdir "%RELEASE_DIR%"
if errorlevel 1 goto :fail

rem Remove obsolete Finder assets from the previous packaging layout.
if exist "%RELEASE_DIR%\ED-Hotspots-Finder-Rings-and-Planets.exe" del /q "%RELEASE_DIR%\ED-Hotspots-Finder-Rings-and-Planets.exe"
if exist "%RELEASE_DIR%\ED-Hotspots-Finder-Rings-and-Planets-%VERSION%-Windows.zip" del /q "%RELEASE_DIR%\ED-Hotspots-Finder-Rings-and-Planets-%VERSION%-Windows.zip"

copy /y "%DIST_EXE%" "%RELEASE_EXE%" >nul
if errorlevel 1 goto :fail

echo Calculating SHA256 checksum...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$name=[IO.Path]::GetFileName($env:RELEASE_EXE); $hash=Get-FileHash -Algorithm SHA256 -LiteralPath $env:RELEASE_EXE; $lines=if(Test-Path -LiteralPath $env:SHA_FILE){Get-Content -LiteralPath $env:SHA_FILE | Where-Object {-not $_.EndsWith('  '+$name)}}else{@()}; @($lines)+($hash.Hash.ToLowerInvariant()+'  '+$name) | Set-Content -LiteralPath $env:SHA_FILE -Encoding ASCII"
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
