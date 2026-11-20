"""Composition root: builds the object graph for each entry point (dependency injection by hand)."""
import os
import signal
import sys

from . import paths
from .core.settings import SettingsStore
from .ipc.client import OverlayClient
from .ipc.protocol import parse_cli


def store() -> SettingsStore:
    return SettingsStore(paths.config_file())


def run_command(words: list[str]) -> int:
    """`quran-companion cmd next` etc. No Qt import, so shortcuts react instantly."""
    cmd = parse_cli(words)
    if cmd is None:
        print(f"Unknown command: {' '.join(words)}", file=sys.stderr); return 2
    if not OverlayClient().send_raw(cmd.to_text()):
        print("Overlay is not running."); return 1
    return 0


def run_toggle() -> int:
    c = OverlayClient()
    if c.running():
        c.send_raw("quit"); return 0
    return run_overlay([])


def run_overlay(args) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="quran-companion overlay")
    ap.add_argument("--surah", type=int); ap.add_argument("--ayah", type=int)
    ap.add_argument("--mode", choices=["recite", "memorize", "manual"]); ap.add_argument("--size", type=int)
    ap.add_argument("--hidden", action="store_true", help="start with the verses hidden")
    a = ap.parse_args(args)
    st = store()
    kw = {k: v for k, v in vars(a).items() if v is not None and k != "hidden"}
    if "surah" in kw:
        kw.setdefault("ayah", 1); kw.update(range_from=kw["ayah"], range_to=0)
    if kw: st.update(**kw)
    if OverlayClient().running():
        print("Already running. Use: quran-overlay.sh quit"); return 0

    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")   # XWayland: always-on-top + click-through on GNOME
    from PySide6.QtWidgets import QApplication

    from .data.repository import default_repository
    from .overlay.controller import OverlayController
    from .playback.player import FfplayPlayer

    app = QApplication(sys.argv[:1])
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    ctl = OverlayController(default_repository(), st, FfplayPlayer(), paths.socket_path(), start_hidden=a.hidden)
    app.aboutToQuit.connect(ctl.shutdown)
    ctl.start()
    return app.exec()


DESKTOP_ENTRY = """[Desktop Entry]
Type=Application
Name=Quran Companion
Name[ar]=رفيق التلاوة
Comment=Read, listen and memorize the Quran while you work
Comment[ar]=تلاوة وحفظ القرآن الكريم أثناء عملك
Exec={exec} ui
Icon={icon}
Terminal=false
Categories=Education;AudioVideo;
"""


def install_desktop_entry() -> int:
    """Write the app-menu entry (~/.local/share/applications/quran-subs.desktop)."""
    launcher = os.path.join(os.path.dirname(paths.PKG), "quran-overlay.sh")
    path = os.path.expanduser("~/.local/share/applications/quran-subs.desktop")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(DESKTOP_ENTRY.format(exec=launcher, icon=paths.LOGO))
    print(path); return 0


def run_ui() -> int:
    from PySide6.QtWidgets import QApplication

    from .data.repository import default_repository
    from .overlay.painter import register_fonts
    from .settings_ui.background import Background
    from .settings_ui.theme.manager import apply_app_theme
    from .settings_ui.viewmodels import AppViewModel, CatalogViewModel, DownloadsViewModel, PlaybackViewModel
    from .settings_ui.views.main_window import MainWindow
    from .settings_ui.widgets import input_guard

    app = QApplication(sys.argv[:1]); app.setApplicationName("Quran Companion"); app.setDesktopFileName("quran-subs")
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    register_fonts()
    input_guard.install(app)
    st, repo, bg = store(), default_repository(), Background()
    vms = dict(app=AppViewModel(st), catalog=CatalogViewModel(repo, bg),
               playback=PlaybackViewModel(st, OverlayClient()), downloads=DownloadsViewModel(repo, bg))
    holder: dict = {}

    def build(page: int = 0, geometry=None) -> None:
        apply_app_theme(app, st.load())
        w = MainWindow(st, **vms, page=page)
        if geometry is not None: w.setGeometry(geometry)
        w.show()
        old = holder.get("w"); holder["w"] = w
        if old: old.close(); old.deleteLater()

    def rebuild() -> None:
        w = holder["w"]; w.save_state()
        build(w.stack.currentIndex(), w.geometry())

    vms["app"].rebuild_requested.connect(rebuild)
    try:
        app.styleHints().colorSchemeChanged.connect(lambda *_: st.load().theme == "system" and rebuild())
    except AttributeError:
        pass
    build()
    code = app.exec()
    bg.shutdown()
    return code
