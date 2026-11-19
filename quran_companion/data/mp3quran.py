"""Reciters, whole-surah audio and verse timings from mp3quran.net."""
from ..core.models import Reciter, VerseTiming
from .http import WEEK, CachedHttp

API = "https://mp3quran.net/api/v3"
INTRO_MIN_MS = 1500   # an untimed gap this long before verse 1 is the basmala / isti'adha


class Mp3Quran:
    def __init__(self, http: CachedHttp):
        self.http = http

    def reciters(self) -> list[Reciter]:
        """Only reciters that have verse timings (needed to follow the recitation)."""
        reads = self.http.get_json(f"{API}/ayat_timing/reads", "reads.json", WEEK)
        try:
            eng = self.http.get_json(f"{API}/reciters?language=eng", "reciters_eng.json", WEEK)["reciters"]
        except Exception:
            eng = []
        info = {m["server"].rstrip("/"): (r["name"], m["name"]) for r in eng for m in r["moshaf"]}
        out = []
        for r in reads:
            en, style = info.get(r["folder_url"].rstrip("/"), ("", r.get("rewaya", "")))
            out.append(Reciter(r["id"], r["name"], en, style, r["folder_url"], r.get("soar_count", 114)))
        out.sort(key=lambda r: (r.en or r.ar).lower())
        return out

    def audio_url(self, reciter: Reciter, surah: int) -> str:
        return reciter.folder + f"{surah:03d}.mp3"

    def verse_timings(self, reciter: Reciter, surah: int) -> list[VerseTiming]:
        tm = self.http.get_json(f"{API}/ayat_timing?surah={surah}&read={reciter.id}", f"timing/{reciter.id}/{surah}.json")
        if not isinstance(tm, list): return []
        times = sorted((VerseTiming(x["ayah"], x["start_time"], x["end_time"]) for x in tm), key=lambda t: t.start_ms)
        if times and times[0].ayah != 0 and times[0].start_ms > INTRO_MIN_MS:
            times.insert(0, VerseTiming(0, 0, times[0].start_ms))
        return times
