# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['/mnt/c/Users/26958/OneDrive - The University of Hong Kong - Connect/Desktop/AutoCCSettings/ccprofile.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['cryptography', 'cryptography.fernet', 'cryptography.hazmat.primitives.ciphers', 'cryptography.hazmat.primitives', 'cryptography.hazmat.backends', 'ccprofile_app'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='ccprofile',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
