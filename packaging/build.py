"""Build the release files for the system this runs on, into dist/:

  Windows  QuranCompanion-<v>-windows-x64-setup.exe (Inno Setup) and -portable.zip
  macOS    QuranCompanion-<v>-macos-<arch>.dmg
  Linux    QuranCompanion-<v>-linux-x86_64.AppImage and .tar.gz

  python packaging/build.py            (after: pip install -r packaging/requirements-build.txt)

Inno Setup (iscc) and appimagetool are used when found on PATH (or ISCC / APPIMAGETOOL env vars);
otherwise only the portable archive is made.
"""
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PKG = os.path.join(ROOT, "packaging")
DIST = os.path.join(ROOT, "dist")
VERSION = re.search(r'__version__ = "([^"]+)"', open(os.path.join(ROOT, "quran_companion", "__init__.py")).read()).group(1)
APP_ID = "io.github.yakoubbenaisa.QuranCompanion"
NAME = f"QuranCompanion-{VERSION}"


def run(*cmd: str, **kw) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, **kw)


def pyinstaller() -> None:
    if sys.platform == "win32": write_version_file()
    run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", DIST,
        "--workpath", os.path.join(ROOT, "build"), os.path.join(PKG, "quran-companion.spec"))


def write_version_file() -> None:
    """Windows file properties (shown in Explorer and by SmartScreen)."""
    v = tuple(int(x) for x in (VERSION.split(".") + ["0", "0", "0"])[:4])
    with open(os.path.join(PKG, "windows", "version.txt"), "w", encoding="utf-8") as f:
        f.write(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={v}, prodvers={v}),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('CompanyName', 'Quran Companion'),
    StringStruct('FileDescription', 'Quran Companion'),
    StringStruct('FileVersion', '{VERSION}'),
    StringStruct('ProductName', 'Quran Companion'),
    StringStruct('ProductVersion', '{VERSION}'),
    StringStruct('OriginalFilename', 'QuranCompanion.exe')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])])
""")


def windows() -> list[str]:
    app = os.path.join(DIST, "QuranCompanion")
    out = []
    zp = os.path.join(DIST, f"{NAME}-windows-x64-portable.zip")
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for base, _, files in os.walk(app):
            for fn in files:
                p = os.path.join(base, fn)
                z.write(p, os.path.join("QuranCompanion", os.path.relpath(p, app)))
    out.append(zp)
    iscc = os.environ.get("ISCC") or shutil.which("iscc") or r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    if os.path.exists(iscc) or shutil.which(iscc):
        from PIL import Image
        ico = os.path.join(ROOT, "build", "logo.ico")
        Image.open(os.path.join(ROOT, "quran_companion", "resources", "icons", "logo.png")).save(
            ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
        run(iscc, f"/DAppVersion={VERSION}", f"/DSourceDir={app}", f"/DOutputDir={DIST}", f"/DIconFile={ico}",
            f"/DOutputName={NAME}-windows-x64-setup", os.path.join(PKG, "windows", "installer.iss"))
        out.append(os.path.join(DIST, f"{NAME}-windows-x64-setup.exe"))
    return out


def macos() -> list[str]:
    app = os.path.join(DIST, "Quran Companion.app")
    if os.environ.get("MACOS_SIGN_IDENTITY"):          # Developer ID; notarization runs in the workflow
        run("codesign", "--deep", "--force", "--options", "runtime", "--timestamp",
            "--entitlements", os.path.join(PKG, "macos", "entitlements.plist"),
            "--sign", os.environ["MACOS_SIGN_IDENTITY"], app)
    stage = os.path.join(ROOT, "build", "dmg")
    shutil.rmtree(stage, ignore_errors=True); os.makedirs(stage)
    shutil.copytree(app, os.path.join(stage, "Quran Companion.app"), symlinks=True)
    os.symlink("/Applications", os.path.join(stage, "Applications"))
    dmg = os.path.join(DIST, f"{NAME}-macos-{platform.machine()}.dmg")
    if os.path.exists(dmg): os.remove(dmg)
    run("hdiutil", "create", "-volname", "Quran Companion", "-srcfolder", stage, "-ov", "-format", "UDZO", dmg)
    return [dmg]


def linux() -> list[str]:
    app = os.path.join(DIST, "QuranCompanion")
    arch = platform.machine()
    out = []
    tgz = os.path.join(DIST, f"{NAME}-linux-{arch}.tar.gz")
    with tarfile.open(tgz, "w:gz") as t:
        t.add(app, arcname="QuranCompanion")
    out.append(tgz)
    tool = os.environ.get("APPIMAGETOOL") or shutil.which("appimagetool")
    if tool:
        appdir = os.path.join(ROOT, "build", "AppDir")
        shutil.rmtree(appdir, ignore_errors=True)
        shutil.copytree(app, os.path.join(appdir, "usr", "lib", "quran-companion"), symlinks=True)
        os.makedirs(os.path.join(appdir, "usr", "share", "metainfo"))
        shutil.copy(os.path.join(PKG, "linux", f"{APP_ID}.metainfo.xml"), os.path.join(appdir, "usr", "share", "metainfo"))
        shutil.copy(os.path.join(PKG, "linux", f"{APP_ID}.desktop"), appdir)
        shutil.copy(os.path.join(ROOT, "quran_companion", "resources", "icons", "logo.png"), os.path.join(appdir, f"{APP_ID}.png"))
        with open(os.path.join(appdir, "AppRun"), "w") as f:
            f.write('#!/bin/sh\nHERE="$(dirname "$(readlink -f "$0")")"\nexec "$HERE/usr/lib/quran-companion/QuranCompanion" "$@"\n')
        os.chmod(os.path.join(appdir, "AppRun"), 0o755)
        img = os.path.join(DIST, f"{NAME}-linux-{arch}.AppImage")
        run(tool, "--no-appstream", appdir, img, env={**os.environ, "ARCH": arch})
        out.append(img)
    return out


if __name__ == "__main__":
    pyinstaller()
    files = windows() if sys.platform == "win32" else macos() if sys.platform == "darwin" else linux()
    print("\nBuilt:\n  " + "\n  ".join(files))
