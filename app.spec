# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Claude Usage Monitor.

Build with: `pyinstaller --noconfirm app.spec`
or via the orchestrator: `py build.py`.

Output: dist/ClaudeUsageMonitor/ (folder distribution; faster startup
than --onefile and easier for Inno Setup to package).
"""

a = Analysis(
    ["app.pyw"],
    pathex=[],
    binaries=[],
    datas=[
        ("logo.png", "."),
        ("icon.png", "."),
    ],
    hiddenimports=[
        "pystray._win32",
        "PIL._tkinter_finder",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest",
        "numpy",
        "IPython",
        "jupyter",
        "notebook",
        "matplotlib",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ClaudeUsageMonitor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ClaudeUsageMonitor",
)
