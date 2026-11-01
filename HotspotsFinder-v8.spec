# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['hotspots_finder_gui_v8_final.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('app.ico', '.'),
        ('ED_Hotspots_Finder.png', '.'),
    ],
    hiddenimports=[
        'edmc_plugin.EDHF_Community_Navigator.api_credentials',
        'edmc_plugin.EDHF_Community_Navigator.batch_protocol',
        'edmc_plugin.EDHF_Community_Navigator.sync_state_lock',
        'edmc_plugin.EDHF_Community_Navigator.sync_plan',
        'edmc_plugin.EDHF_Community_Navigator.sync_preview_dialog',
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
