"""Offscreen smoke tests of the settings window and the overlay controller."""
import pytest
from conftest import ALAFASY

from quran_companion import system
from quran_companion.core.settings import STYLE_KEYS
from quran_companion.ipc.client import OverlayClient
from quran_companion.ipc.protocol import Cmd, Command
from quran_companion.playback.player import FakePlayer

pytestmark = pytest.mark.usefixtures("qapp_fonts")


class FakeSync:
    """Stands in for SyncService: recognises Al-Kahf and 'syncs' it instantly."""
    def __init__(self, repo):
        self.repo = repo

    def inspect(self, src):
        from quran_companion.data.media import MediaInfo
        from quran_companion.sync.service import Inspection
        if "bad" in src: raise ValueError("not a link or an existing file")
        if "nosurah" in src:
            return Inspection(MediaInfo(src, "video", "Beautiful recitation", 1500.0, "k"), None, None, False)
        return Inspection(MediaInfo(src, "video", "سورة الكهف | Mishary Alafasy", 1500.0, "k"), 18,
                          self.repo.find_reciter(ALAFASY), False)

    def create(self, ins, surah, a, b, progress=lambda s, f: None, cancel=lambda: False):
        from quran_companion.core.models import MyRecitation, VerseTiming
        progress("download", 0.3); progress("match", 0.9)
        ts = [VerseTiming(n, n * 10000, n * 10000 + 9000) for n in range(0, 111)]
        return self.repo.mine.save(MyRecitation(self.repo.mine.new_id(), "Al-Kahf · Alafasy", ins.info.source, "/x.m4a",
                                                surah, list(range(111)), ts, confident=0.95, reciter_name="Mishary Alafasi"))


@pytest.fixture
def window_factory(repo, store, tmp_path, qtbot):
    from PySide6.QtWidgets import QApplication

    from quran_companion.data.my_recitations import MyRecitations
    from quran_companion.settings_ui.background import Background
    from quran_companion.settings_ui.theme.manager import apply_app_theme
    from quran_companion.settings_ui.viewmodels import AppViewModel, CatalogViewModel, DownloadsViewModel, MineViewModel, PlaybackViewModel
    from quran_companion.settings_ui.views.main_window import MainWindow
    bg = Background()
    repo.mine = MyRecitations(str(tmp_path / "mine"))

    def make(lang="en", theme="dark"):
        store.update(ui_lang=lang, theme=theme, reciter=ALAFASY)
        apply_app_theme(QApplication.instance(), store.load())
        vms = dict(app=AppViewModel(store), catalog=CatalogViewModel(repo, bg),
                   playback=PlaybackViewModel(store, OverlayClient(str(tmp_path / "none.sock"))),
                   downloads=DownloadsViewModel(repo, bg), mine=MineViewModel(repo, bg, lambda: FakeSync(repo)))
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
    assert not vms["playback"].status.running and w.bar.pill.objectName() == "pillOff"
    assert not w.grab().isNull()


def test_window_rebuild_keeps_choices(window_factory, store):
    w, _ = window_factory()
    w.recite.modeg.button(1).click()            # memorize
    w.appearance.size.setValue(55)
    w.save_state()
    s = store.load()
    assert s.mode == "memorize" and s.size == 55


def test_overlay_controller_handles_commands(repo, store, sock_dir, qtbot):
    from quran_companion.overlay.controller import OverlayController
    sock = str(sock_dir / "ov.sock")
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


def test_wheel_over_dropdown_scrolls_page_not_value(qapp):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QApplication, QComboBox, QSpinBox

    from quran_companion.settings_ui.widgets import input_guard
    g = input_guard.install(qapp)
    try:
        cb = QComboBox(); cb.addItems([str(i) for i in range(20)]); cb.setCurrentIndex(5)
        sp = QSpinBox(); sp.setValue(5)
        for w in (cb, sp):
            w.ensurePolished()
            ev = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(), QPoint(0, -120), Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
            QApplication.sendEvent(w, ev)
            assert not ev.isAccepted()      # handed on to the page
        assert cb.currentIndex() == 5 and sp.value() == 5
    finally:
        qapp.removeEventFilter(g)


def test_click_on_searchable_dropdown_text_opens_list_and_typing_searches(qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QComboBox, QFontComboBox

    from quran_companion.settings_ui.widgets import input_guard
    g = input_guard.install(qapp)
    try:
        cb = QComboBox(); cb.setEditable(True); cb.addItems(["1. Al-Fatiha", "2. Al-Baqara", "36. Yaseen"]); cb.show()
        QTest.qWait(10)
        QTest.mouseClick(cb.lineEdit(), Qt.LeftButton, Qt.NoModifier, cb.lineEdit().rect().center())
        QTest.qWait(30)
        assert cb.view().isVisible()
        QTest.keyClick(cb.view(), Qt.Key_Y, Qt.NoModifier)
        QTest.qWait(30)
        assert not cb.view().isVisible() and cb.lineEdit().text() == "y"
        fc = QFontComboBox(); fc.resize(300, 36); fc.show(); QTest.qWait(30)
        assert fc.view().window().width() == 300
    finally:
        qapp.removeEventFilter(g)



@pytest.mark.parametrize("lang", ["en", "ar"])
def test_link_or_file_syncs_and_selects_the_recording(window_factory, qtbot, lang):
    w, vms = window_factory(lang, "dark")
    r = w.recite
    r.srcg.button(1).click()
    assert r.sources.currentWidget() is r.link
    r.link.src.setText("bad input"); r.link._check()
    qtbot.waitUntil(lambda: "not a link" in r.link.info.text(), timeout=5000)
    assert not r.link.b_sync.isEnabled()
    r.link.src.setText("https://youtube.com/watch?v=abc"); r.link._check()
    qtbot.waitUntil(lambda: r.link.b_sync.isEnabled(), timeout=5000)
    assert r.surah_number() == 18                      # recognised from the title
    r.link.b_sync.click()
    qtbot.waitUntil(lambda: r.reciter() is not None and r.reciter().mine, timeout=5000)
    assert r.reclist.count() == 116 and r.reciter().ar == "Al-Kahf · Alafasy"
    assert r.link.list.count() == 1 and "Al-Kahf" in r.link.list.item(0).text()
    vals = w.all_values()
    assert vals["reciter"] == r.reciter().id and vals["surah"] == 18
    w.go(2)
    assert not w.downloads.b_all.isEnabled()          # nothing to download: it's on disk


@pytest.mark.skipif(not system.BROWSER_FOLLOW, reason="following a browser video is Linux only")
def test_video_in_browser_sync_then_follow_values(window_factory, qtbot, monkeypatch):
    from quran_companion.playback.mpris import Media
    from quran_companion.settings_ui.views.browser_panel import BrowserMediaViewModel
    monkeypatch.setattr(BrowserMediaViewModel, "refresh", lambda self: None)      # never touch the real browsers
    w, vms = window_factory("en", "light")
    r = w.recite
    r.srcg.button(2).click()
    b = r.browser
    assert r.sources.currentWidget() is b
    vid = Media("org.mpris.MediaPlayer2.firefox.instance_1_9", "Firefox", "سورة الكهف | Mishary Alafasy",
                "https://www.youtube.com/watch?v=abc123&t=5", "Playing", 0.0)
    b._fill([vid])
    assert b.selected == vid and b.b_sync.isEnabled() and not b.b_follow.isEnabled()
    assert w.all_values()["follow_player"] == ""                 # nothing synced yet: not following
    b.b_sync.click()                                              # FakeSync recognises Al-Kahf and saves it
    qtbot.waitUntil(lambda: b.b_follow.isEnabled(), timeout=5000)
    vals = w.all_values()
    assert vals["follow_player"] == "org.mpris.MediaPlayer2.firefox" and "abc123" in vals["follow_url"]
    assert repo_mine_id(vals) and vals["mode"] == "recite" and vals["surah"] == 18
    r.srcg.button(0).click()
    assert w.all_values()["follow_player"] == ""                  # back on the reciter list: plays the audio itself


@pytest.mark.skipif(not system.BROWSER_FOLLOW, reason="following a browser video is Linux only")
def test_video_in_browser_without_surah_in_title_asks_for_it(window_factory, qtbot, monkeypatch):
    from quran_companion.playback.mpris import Media
    from quran_companion.settings_ui.views.browser_panel import BrowserMediaViewModel
    monkeypatch.setattr(BrowserMediaViewModel, "refresh", lambda self: None)
    w, vms = window_factory("en", "light")
    r = w.recite
    r.srcg.button(2).click()
    b = r.browser
    b._fill([Media("org.mpris.MediaPlayer2.firefox.instance_1_9", "Firefox", "Beautiful recitation",
                   "https://www.youtube.com/watch?v=nosurah123", "Playing", 0.0)])
    b.b_sync.click()
    qtbot.waitUntil(lambda: b.b_sync.text().startswith("Sync as"), timeout=5000)
    assert not vms["mine"].recordings()                            # nothing synced on a guess
    r.set_surah(11)
    assert "Hud" in b.b_sync.text()
    b.b_sync.click()
    qtbot.waitUntil(lambda: b.b_follow.isEnabled(), timeout=5000)
    assert vms["mine"].recordings()[0].surah == 11


def repo_mine_id(vals):
    from quran_companion.core.models import MINE_BASE
    return vals["reciter"] >= MINE_BASE
