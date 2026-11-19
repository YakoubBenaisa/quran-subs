"""Word timings from quran.com, used as *relative* positions inside each verse to turn pages exactly.

quran.com only has a few famous reciters; they are matched to mp3quran reciters by name and style.
"""
from ..core.models import Reciter
from ..core.text import norm
from .http import CachedHttp

API = "https://api.qurancdn.com/api/qdc/audio/reciters"

KEYS = {7: ["afasi"], 3: ["sudais", "sudaes"], 4: ["shatri"], 5: ["rifai"], 6: ["husari"],
        10: ["shuraim", "shurim"], 9: ["minshawi", "menshawi"], 2: ["abdulbasit", "abdulbaset"],
        97: ["dosari", "dusari"], 161: ["tunaiji"]}
MUJAWWAD = {2: 1}
MUALLIM = {6: 12}


def match_reciter(rec: Reciter) -> int | None:
    st = rec.style.lower()
    if "hafs" not in st: return None
    n = norm(rec.en or "")
    for qid, keys in KEYS.items():
        if any(norm(k) in n for k in keys):
            if "jawwad" in st: return MUJAWWAD.get(qid)
            if "lim" in st or "allim" in st: return MUALLIM.get(qid)
            return qid
    return None


class QuranCom:
    def __init__(self, http: CachedHttp):
        self.http = http

    def word_fractions(self, reciter: Reciter, surah: int) -> dict[int, dict[int, float]]:
        """{ayah: {word position (1-based): fraction of the verse duration}}; {} when not available."""
        qid = match_reciter(reciter)
        if not qid: return {}
        d = self.http.get_json(f"{API}/{qid}/audio_files?chapter={surah}&segments=true", f"qdc/{qid}/{surah}.json")
        out: dict[int, dict[int, float]] = {}
        for v in d["audio_files"][0]["verse_timings"]:
            a, b = v["timestamp_from"], v["timestamp_to"]
            if b <= a: continue
            fr: dict[int, float] = {}
            for x in v.get("segments") or []:
                if len(x) == 3 and int(x[0]) not in fr: fr[int(x[0])] = max(0.0, (x[1] - a) / (b - a))
            if fr: out[int(v["verse_key"].split(":")[1])] = fr
        return out
