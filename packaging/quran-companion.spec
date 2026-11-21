# PyInstaller spec for Windows, macOS and Linux:  pyinstaller packaging/quran-companion.spec
# Output: dist/QuranCompanion/ (Windows, Linux) or dist/Quran Companion.app (macOS).
import os
import re
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))  # noqa: F821 - SPECPATH is set by PyInstaller
VERSION = re.search(r'__version__ = "([^"]+)"', open(os.path.join(ROOT, "quran_companion", "__init__.py"), encoding="utf-8").read()).group(1)
APP_ID = "io.github.yakoubbenaisa.QuranCompanion"
WIN, MAC = sys.platform == "win32", sys.platform == "darwin"

datas = [(os.path.join(ROOT, "quran_companion", "resources"), "quran_companion/resources")]
datas += collect_data_files("imageio_ffmpeg", subdir="binaries")          # the ffmpeg binary
hidden = collect_submodules("yt_dlp") + collect_submodules("quran_companion")
hidden += ["PySide6.QtMultimedia"]
if MAC: hidden += collect_submodules("pynput")
if not (WIN or MAC): hidden += collect_submodules("jeepney")

# Qt parts the app never uses: keeps the download small
EXCLUDE = ["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick", "PySide6.Qt3DCore",
           "PySide6.Qt3DRender", "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtQuick3D", "PySide6.QtCharts",
           "PySide6.QtDataVisualization", "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtSql", "PySide6.QtTest",
           "PySide6.QtDesigner", "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtSensors", "PySide6.QtSerialPort",
           "PySide6.QtLocation", "PySide6.QtPositioning", "PySide6.QtRemoteObjects", "PySide6.QtScxml",
           "PySide6.QtSpatialAudio", "PySide6.QtTextToSpeech", "PySide6.QtWebSockets", "PySide6.QtHttpServer",
           "tkinter", "matplotlib", "scipy", "pytest", "IPython"]

ICON = os.path.join(ROOT, "quran_companion", "resources", "icons", "logo.png")   # converted to .ico/.icns (Pillow)

a = Analysis([os.path.join(SPECPATH, "entry.py")], pathex=[ROOT], datas=datas, hiddenimports=hidden,  # noqa: F821
             excludes=EXCLUDE, noarchive=False)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="QuranCompanion",  # noqa: F821
          console=False, icon=ICON, disable_windowed_traceback=False,
          version=os.path.join(SPECPATH, "windows", "version.txt") if WIN else None)
coll = COLLECT(exe, a.binaries, a.datas, name="QuranCompanion", strip=False, upx=False)  # noqa: F821

if MAC:
    app = BUNDLE(coll, name="Quran Companion.app", icon=ICON, bundle_identifier=APP_ID,  # noqa: F821
                 version=VERSION,
                 info_plist={
                     "CFBundleDisplayName": "Quran Companion",
                     "CFBundleShortVersionString": VERSION,
                     "CFBundleVersion": VERSION,
                     "NSHighResolutionCapable": True,
                     "LSMinimumSystemVersion": "11.0",
                     "LSApplicationCategoryType": "public.app-category.education",
                     "CFBundleDevelopmentRegion": "en",
                     "CFBundleLocalizations": ["en", "ar"],
                 })
