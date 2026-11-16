# -*- mode: python ; coding: utf-8 -*-
import json
from pathlib import Path

release_root = Path(SPECPATH)
release_manifest = json.loads((release_root / 'release_manifest.json').read_text(encoding='utf-8'))
for source in release_manifest['finder_sources']:
    if not (release_root / source).is_file():
        raise FileNotFoundError(source)
for source in release_manifest['finder_shared_sources']:
    if not (release_root / 'edmc_plugin' / 'EDHF_Community_Navigator' / source).is_file():
        raise FileNotFoundError(source)

a = Analysis(
    ['hotspots_finder_gui_v8_final.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('app.ico', '.'),
        ('ED_Hotspots_Finder.png', '.'),
        ('Mahon_logo.png', '.'),
    ],
    hiddenimports=[Path(source).stem for source in release_manifest['finder_sources']
                   if source != 'hotspots_finder_gui_v8_final.py'] + [
        'edmc_plugin.EDHF_Community_Navigator.' + Path(source).stem
        for source in release_manifest['finder_shared_sources']
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'google',
        'googleapiclient',
        'google_auth_oauthlib',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ED Hotspots Finder - Rings & Planets',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['app.ico'],
    version='version_info_v8.txt',
)
