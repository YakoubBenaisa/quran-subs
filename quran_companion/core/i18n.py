"""Interface languages: one JSON file per language in resources/lang (copy en.json to add one)."""
import json
import locale
import os

from .. import paths


class Translator:
    def __init__(self, lang_dir: str = paths.LANG_DIR):
        self.lang_dir = lang_dir
        self._en: dict = {}
        self._cur: dict = {}
        self.code = "en"
        self.set("en")

    def languages(self) -> list[tuple[str, str, str]]:
        """[(code, display name, 'ltr'|'rtl')]"""
        out = []
        for fn in sorted(os.listdir(self.lang_dir)) if os.path.isdir(self.lang_dir) else []:
            if fn.endswith(".json"):
                d = self._read(fn[:-5])
                if d: out.append((fn[:-5], d.get("_name", fn[:-5]), d.get("_dir", "ltr")))
        return out

    def _read(self, code: str) -> dict:
        try:
            with open(os.path.join(self.lang_dir, code + ".json"), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def set(self, code: str | None) -> str:
        if code in ("", "auto", None):
            sysl = (os.environ.get("LANG") or locale.getlocale()[0] or "en")[:2]
            code = sysl if os.path.exists(os.path.join(self.lang_dir, sysl + ".json")) else "en"
        self._en = self._read("en")
        self._cur = self._read(code) or self._en
        self.code = code if self._cur is not self._en or code == "en" else "en"
        return self.code

    @property
    def rtl(self) -> bool:
        return self._cur.get("_dir", "ltr") == "rtl"

    def t(self, key: str, **kw) -> str:
        s = self._cur.get(key) or self._en.get(key) or key
        try:
            return s.format(**kw) if kw else s
        except (KeyError, IndexError, ValueError):
            return s


# the process-wide translator used by the views
tr = Translator()


def T(key: str, **kw) -> str:
    return tr.t(key, **kw)


def rtl() -> bool:
    return tr.rtl
