import json

import pytest

from quran_companion.core.settings import Settings, SettingsStore, from_dict


def test_defaults(store):
    s = store.load()
    assert s == Settings() and s.mode == "recite" and s.max_lines == 3


def test_migrates_old_files():
    assert from_dict({"reciter": "ar.alafasy"}).reciter == 0                 # v1
    assert from_dict({"follow": True}).mode == "manual"                      # v2
    assert from_dict({"follow": False, "mode": "memorize"}).mode == "memorize"
    assert from_dict({"mode": "nonsense", "theme": "pink"}) == Settings()


def test_update_only_touches_given_keys_and_keeps_unknown(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"surah": 36, "custom_key": 1, "follow": True}))
    st = SettingsStore(str(p))
    s = st.update(ayah=5)
    assert (s.surah, s.ayah, s.mode) == (36, 5, "manual")
    raw = json.loads(p.read_text())
    assert raw["custom_key"] == 1 and "follow" not in raw and raw["ayah"] == 5


def test_unknown_setting_is_rejected(store):
    with pytest.raises(KeyError):
        store.update(colour="red")


def test_corrupt_file_falls_back_to_defaults(tmp_path):
    p = tmp_path / "s.json"; p.write_text("{not json")
    assert SettingsStore(str(p)).load() == Settings()
