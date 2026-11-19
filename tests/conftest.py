import json
import os
import shutil
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from quran_companion.core.settings import SettingsStore  # noqa: E402
from quran_companion.data.alquran_cloud import AlQuranCloud  # noqa: E402
from quran_companion.data.http import CachedHttp  # noqa: E402
from quran_companion.data.library import Library  # noqa: E402
from quran_companion.data.mp3quran import Mp3Quran  # noqa: E402
from quran_companion.data.qurancom import QuranCom  # noqa: E402
from quran_companion.data.repository import QuranRepository  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "fixtures")
ALAFASY = 123


class OfflineHttp(CachedHttp):
    """Never touches the network: cached fixture files are always used (stale is fine)."""
    def fetch(self, url, timeout=None):
        raise OSError(f"offline test: {url}")


@pytest.fixture
def cache_dir(tmp_path):
    d = tmp_path / "cache"
    shutil.copytree(FIXTURES, d)
    return str(d)


@pytest.fixture
def repo(cache_dir, tmp_path):
    http = OfflineHttp(cache_dir)
    mp3 = Mp3Quran(http)
    return QuranRepository(AlQuranCloud(http), mp3, mp3, QuranCom(http), Library(str(tmp_path / "lib"), http))


@pytest.fixture
def store(tmp_path):
    return SettingsStore(str(tmp_path / "settings.json"))


@pytest.fixture(scope="session")
def golden():
    with open(os.path.join(HERE, "golden", "golden.json"), encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def qapp_fonts():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from quran_companion.overlay.painter import register_fonts
    register_fonts()
    return app


class FakeMeasurer:
    """Every character is 10 px wide (translation scaled), so layouts are predictable."""
    def width(self, text, kind, scale=1.0):
        return len(text) * 10 * (scale if kind == "tr" else 1.0)


class Recorder:
    """Session listener that records what would be shown."""
    def __init__(self):
        self.views = []

    def on_view(self, v):
        self.views.append(v)

    def keys(self):
        out = []
        for v in self.views:
            k = (v.kind, v.ayah, v.index) if v.kind == "page" else (v.kind, v.ayah) if v.kind in ("hint", "blank") else ("message", v.text)
            if not out or out[-1] != k: out.append(k)
        return out
