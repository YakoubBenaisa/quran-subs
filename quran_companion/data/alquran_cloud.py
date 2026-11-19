"""Quran text and translations from api.alquran.cloud."""
from ..core.models import Ayah, SurahInfo, Translation
from ..core.text import strip_basmala
from .http import WEEK, CachedHttp

API = "https://api.alquran.cloud/v1"


class AlQuranCloud:
    def __init__(self, http: CachedHttp):
        self.http = http

    def surahs(self) -> list[SurahInfo]:
        data = self.http.get_json(f"{API}/surah", "surahs.json")["data"]
        return [SurahInfo(s["number"], s["name"], s["englishName"], s["englishNameTranslation"],
                          s["numberOfAyahs"], s["revelationType"]) for s in data]

    def translations(self) -> list[Translation]:
        data = self.http.get_json(f"{API}/edition?format=text&type=translation", "translations.json", WEEK)["data"]
        return [Translation(e["identifier"], e["language"], e["englishName"]) for e in data]

    def surah_text(self, surah: int, translation: str = "") -> dict[int, Ayah]:
        eds = "quran-uthmani" + (f",{translation}" if translation else "")
        data = self.http.get_json(f"{API}/surah/{surah}/editions/{eds}", f"text/{surah}_{translation or 'ar'}.json")["data"]
        ar, tr = data[0]["ayahs"], (data[1]["ayahs"] if translation else None)
        out = {}
        for i, a in enumerate(ar):
            text = strip_basmala(a["text"], surah) if i == 0 else a["text"].replace("﻿", "").strip()
            out[a["numberInSurah"]] = Ayah(a["numberInSurah"], text, tr[i]["text"] if tr else "")
        return out
