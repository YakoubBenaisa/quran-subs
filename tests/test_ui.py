"""Offscreen smoke tests of the settings window and the overlay controller."""
import pytest
from conftest import ALAFASY

from quran_companion.core.settings import STYLE_KEYS
from quran_companion.ipc.client import OverlayClient
from quran_companion.ipc.protocol import Cmd, Command
from quran_companion.playback.player import FakePlayer

pytestmark = pytest.mark.usefixtures("qapp_fonts")


@pytest.fixture
def window_factory(repo, store, tmp_path, qtbot):
    from PySide6.QtWidgets import QApplication

    from quran_companion.settings_ui.background import Background
    from quran_companion.settings_ui.theme.manager import apply_app_theme
    from quran_companion.settings_ui.viewmodels import AppViewModel, CatalogViewModel, DownloadsViewModel, PlaybackViewModel
    from quran_companion.settings_ui.views.main_window import MainWindow
    bg = Background()

    def make(lang="en", theme="dark"):
        store.update(ui_lang=lang, theme=theme, reciter=ALAFASY)
        apply_app_theme(QApplication.instance(), store.load())
        vms = dict(app=AppViewModel(store), catalog=CatalogViewModel(repo, bg),
                   playback=PlaybackViewModel(store, OverlayClient(str(tmp_path / "none.sock"))),
                   downloads=DownloadsViewModel(repo, bg))
        w = MainWindow(store, **vms)
        qtbot.addWidget(w); w.show()
        qtbot.waitUntil(lambda: vms["catalog"].ready, timeout=10000)
        return w, vms
    yield make
    bg.shutdown()


@pytest.mark.parametrize("lang, theme", [("en", "dark"), ("ar", "light"), ("ar", "dark"), ("en", "light")])
def test_settings_window_builds_and_works(window_factory, tmp_path, lang, theme):
    from PySide6.QtCore import Qt
    w, vms = window_factory(lang, theme)
    r = w.recite
    assert r.reclist.count() == 115 and r.reciter().id == ALAFASY
    assert w.layoutDirection() == (Qt.RightToLeft if lang == "ar" else Qt.LeftToRight)
    r.search.setText("ahmed bin taleb")
    visible = [r.reclist.item(i).data(Qt.UserRole).en for i in range(r.reclist.count()) if not r.reclist.isRowHidden(i)]
    assert visible == ["Ahmad Talib bin Humaid"]
    r.search.clear()
    vals = w.all_values()
    assert set(STYLE_KEYS) <= set(vals) and vals["reciter"] == ALAFASY and vals["mode"] in ("recite", "memorize", "manual")
    w.go(2)
    assert w.downloads.name.text() in ("Mishary Alafasi", "مشاري العفاسي")
    assert not vms["playback"].status.running and w.bar.pill.objectName() == "pillOff"
    assert not w.grab().isNull()


def test_window_rebuild_keeps_choices(window_factory, store):
    w, _ = window_factory()
    w.recite.modeg.button(1).click()            # memorize
    w.appearance.size.setValue(55)
    w.save_state()
    s = store.load()
    assert s.mode == "memorize" and s.size == 55


def test_overlay_controller_handles_commands(repo, store, tmp_path, qtbot):
    from quran_companion.overlay.controller import OverlayController
    sock = str(tmp_path / "ov.sock")
    store.update(surah=112, ayah=1, mode="manual", range_from=1, range_to=0)
    ctl = OverlayController(repo, store, FakePlayer(), sock)
    ctl.start()
    try:
        qtbot.waitUntil(lambda: ctl.session.cur == 1, timeout=5000)
        c = OverlayClient(sock)
        assert c.up_to_date()
        c.send(Cmd.NEXT); qtbot.waitUntil(lambda: ctl.session.cur == 2, timeout=3000)
        c.send(Command(Cmd.VISIBLE, {"on": False})); qtbot.waitUntil(lambda: ctl.window.hidden, timeout=3000)
        assert store.load().visible is False
        c.send(Cmd.NEXT); qtbot.waitUntil(lambda: ctl.session.cur == 3, timeout=3000)   # keeps going while hidden
        c.send(Cmd.HIDE); qtbot.waitUntil(lambda: not ctl.window.hidden, timeout=3000)
        c.send_raw("surah 1 3"); qtbot.waitUntil(lambda: (ctl.session.surah, ctl.session.cur) == (1, 3), timeout=3000)
        c.send(Cmd.BIGGER); qtbot.waitUntil(lambda: store.load().size == 44, timeout=3000)
    finally:
        ctl.shutdown()
