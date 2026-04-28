"""End-to-end build for Claude Usage Monitor.

Steps:
  1. Ensure runtime deps + PyInstaller are installed.
  2. Generate icon.ico from icon.png (used by both PyInstaller and Inno Setup).
  3. Run PyInstaller to produce dist/ClaudeUsageMonitor/.
  4. Run Inno Setup (ISCC.exe) to produce dist-installer/ClaudeUsageMonitor-Setup-<v>.exe.
     If Inno Setup isn't installed, prints download instructions and stops
     at step 3.

Run with: `py build.py`.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
DIST = ROOT / "dist"
INSTALLER_OUT = ROOT / "dist-installer"

ISCC_CANDIDATES = [
    Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
    Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
    Path(r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe"),
    # Per-user winget install location:
    Path.home() / "AppData" / "Local" / "Programs" / "Inno Setup 6" / "ISCC.exe",
]


def step(msg: str):
    print(f"\n=== {msg} ===")


def run(cmd: list[str], cwd: Path | None = None):
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=cwd or ROOT, check=True)


def ensure_build_deps():
    step("Installing build dependencies")
    run([sys.executable, "-m", "pip", "install", "-q",
         "-r", str(ROOT / "requirements.txt"),
         "pyinstaller>=6.0"])


def ensure_ico():
    step("Generating icon.ico from icon.png")
    # Import lazily so a fresh checkout can install deps first.
    sys.path.insert(0, str(ROOT))
    from app import ensure_ico as _ensure  # type: ignore
    ico = _ensure()
    if ico is None:
        raise SystemExit("Failed to generate icon.ico")
    print(f"  -> {ico}")


def clean():
    step("Cleaning previous build artifacts")
    for d in (DIST, ROOT / "build", INSTALLER_OUT):
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
            print(f"  removed {d}")


def build_exe():
    step("Building exe with PyInstaller")
    run([sys.executable, "-m", "PyInstaller", "--noconfirm",
         "--clean", str(ROOT / "app.spec")])
    out = DIST / "ClaudeUsageMonitor" / "ClaudeUsageMonitor.exe"
    if not out.exists():
        raise SystemExit(f"PyInstaller did not produce {out}")
    print(f"  -> {out}")


def build_installer() -> Path | None:
    step("Building installer with Inno Setup")
    iscc = next((p for p in ISCC_CANDIDATES if p.exists()), None)
    if iscc is None:
        print("  Inno Setup compiler (ISCC.exe) not found.")
        print("  Install from https://jrsoftware.org/isdl.php (free) and re-run.")
        print("  Skipping installer — the unpackaged build is in dist/ClaudeUsageMonitor/.")
        return None
    run([str(iscc), str(ROOT / "installer.iss")])
    out = next(INSTALLER_OUT.glob("ClaudeUsageMonitor-Setup-*.exe"), None)
    if out is None:
        raise SystemExit("Inno Setup ran but no installer .exe was produced")
    print(f"  -> {out}")
    return out


def main():
    ensure_build_deps()
    ensure_ico()
    clean()
    build_exe()
    installer = build_installer()
    print()
    if installer:
        print(f"DONE.  Distribute: {installer}")
    else:
        print("DONE (without installer).  Distribute the dist/ClaudeUsageMonitor/ folder.")


if __name__ == "__main__":
    main()
