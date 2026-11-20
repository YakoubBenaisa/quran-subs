"""Composition root: builds the object graph for each entry point (dependency injection by hand)."""
import os
import signal
import sys

from . import paths, system
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


def make_sync_service(repo):
    from .data.http import CachedHttp
    from .data.media import MediaFetcher
    from .sync.service import SyncService
    assert repo.mine is not None
    return SyncService(repo, MediaFetcher(repo.mine.media_dir, CachedHttp(paths.cache_dir())), repo.mine)


def make_corrector(repo):
    """(reciter id, ayah, starts at s) -> new timings, for corrections of the user's own recordings."""
    service = None

    def correct(rid: int, ayah: int, at: float):
        nonlocal service
        if service is None: service = make_sync_service(repo)     # numpy etc. only when needed
        m = repo.my_recitation(rid)
        return service.correct(m, ayah, at).timings if m else []
    return correct


def make_player(repo, st):
    """Audio (ffplay if installed, else Qt Multimedia), or following a browser video for the user's own
    recordings (Linux). QOV_PLAYER=qt|ffplay chooses."""
    from .playback.browser_player import BrowserPlayer
    from .playback.player import FfplayPlayer, RoutingPlayer
    service = None

    def features_for(audio: str) -> str:
        nonlocal service
        if service is None: service = make_sync_service(repo)
        return service.features_for_audio(audio)
    choice = os.environ.get("QOV_PLAYER") or ("ffplay" if system.LINUX and system.tool("ffplay") else "qt")
    if choice == "ffplay": own = FfplayPlayer(system.tool("ffplay") or "ffplay")
    else:
        from .overlay.qt_player import QtPlayer
        own = QtPlayer()
    return RoutingPlayer(own, BrowserPlayer(), st.load, features_for)


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

    if system.LINUX:
        os.environ.setdefault("QT_QPA_PLATFORM", "xcb")   # XWayland: always-on-top + click-through on GNOME
    from PySide6.QtWidgets import QApplication

    from .data.repository import default_repository
    from .overlay.controller import OverlayController
    app = QApplication(sys.argv[:1])
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    repo = default_repository()
    ctl = OverlayController(repo, st, make_player(repo, st), paths.socket_path(), start_hidden=a.hidden,
                            corrector=make_corrector(repo))
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


def launcher_command() -> str:
    """How the desktop should start this app: the AppImage, the packaged binary or the source launcher."""
    if os.environ.get("APPIMAGE"): return os.environ["APPIMAGE"]
    src = os.path.join(os.path.dirname(paths.PKG), "quran-overlay.sh")
    if not system.FROZEN and os.path.exists(src): return src
    return " ".join(f'"{a}"' if " " in a else a for a in system.self_command())


def install_desktop_entry() -> int:
    """Write the app-menu entry (~/.local/share/applications/quran-subs.desktop). Linux only:
    the Windows installer and the macOS app bundle add themselves to the menu."""
    if not system.LINUX:
        print("Not needed on this system: the installer adds Quran Companion to the menu."); return 0
    launcher = launcher_command()
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
    from .settings_ui.viewmodels import AppViewModel, CatalogViewModel, DownloadsViewModel, MineViewModel, PlaybackViewModel
    from .settings_ui.views.main_window import MainWindow
    from .settings_ui.widgets import input_guard

    app = QApplication(sys.argv[:1]); app.setApplicationName("Quran Companion"); app.setDesktopFileName("quran-subs")
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    register_fonts()
    input_guard.install(app)
    st, repo, bg = store(), default_repository(), Background()
    vms = dict(app=AppViewModel(st), catalog=CatalogViewModel(repo, bg),
               playback=PlaybackViewModel(st, OverlayClient()), downloads=DownloadsViewModel(repo, bg),
               mine=MineViewModel(repo, bg, lambda: make_sync_service(repo)))
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


SHORTCUTS = [("on/off", "toggle", "q"), ("next", "next", "Right"), ("prev", "prev", "Left"), ("pause", "pause", "space"),
             ("hide", "hide", "h"), ("bigger", "bigger", "Up"), ("smaller", "smaller", "Down"),
             ("next surah", "nextsurah", "Page_Down"), ("previous surah", "prevsurah", "Page_Up"), ("settings", "ui", "s")]


def setup_shortcuts() -> int:
    """GNOME: add the Super+Alt shortcuts as custom keyboard shortcuts (keeps the user's own).
    Windows and macOS: the overlay listens for them itself."""
    import ast
    import subprocess
    if not system.LINUX:
        print(f"Shortcuts ({system.MOD_LABEL}+key) work while the verses are on screen; nothing to set up."); return 0
    schema = "org.gnome.settings-daemon.plugins.media-keys"
    base = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings"
    try:
        cur = subprocess.run(["gsettings", "get", schema, "custom-keybindings"], capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        print("gsettings not found: add the shortcuts in your desktop's keyboard settings instead."); return 1
    cur = cur.strip().removeprefix("@as ")
    have = list(ast.literal_eval(cur)) if cur.startswith("[") else []
    exe = launcher_command()
    for i, (name, cmd, key) in enumerate(SHORTCUTS):
        p = f"{base}/quran{i}/"; k = f"{schema}.custom-keybinding:{p}"
        for field, val in (("name", f"Quran: {name}"), ("command", f"{exe} {cmd}"), ("binding", f"<Super><Alt>{key}")):
            subprocess.run(["gsettings", "set", k, field, val], check=False)
        if p not in have: have.append(p)
    subprocess.run(["gsettings", "set", schema, "custom-keybindings", str(have)], check=False)
    print("Shortcuts added. Super+Alt+S = settings, Super+Alt+Q = start/stop."); return 0
