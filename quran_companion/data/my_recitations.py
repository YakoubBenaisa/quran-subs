"""The user's own recordings: one JSON file each, next to the downloaded audio and the sync cache."""
import json
import os
import time

from ..core.models import MyRecitation, VerseTiming


class MyRecitations:
    def __init__(self, root: str):
        self.root = root

    @property
    def media_dir(self) -> str:
        return os.path.join(self.root, "media")

    @property
    def cache_dir(self) -> str:
        return os.path.join(self.root, "cache")

    def _path(self, rid: int) -> str:
        return os.path.join(self.root, f"{rid}.json")

    def all(self) -> list[MyRecitation]:
        if not os.path.isdir(self.root): return []
        out = []
        for name in os.listdir(self.root):
            if name.endswith(".json") and name[:-5].isdigit():
                r = self.get(int(name[:-5]))
                if r: out.append(r)
        return sorted(out, key=lambda r: -r.created)

    def get(self, rid: int) -> MyRecitation | None:
        try:
            with open(self._path(rid), encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            return None
        return MyRecitation(
            id=rid, title=d.get("title", ""), source=d.get("source", ""), audio=d.get("audio", ""),
            surah=int(d.get("surah", 1)), ayahs=[int(a) for a in d.get("ayahs", [])],
            timings=[VerseTiming(int(a), int(s), int(e)) for a, s, e in d.get("timings", [])],
            anchors={int(k): float(v) for k, v in d.get("anchors", {}).items()},
            confident=float(d.get("confident", 0)), reciter_name=d.get("reciter_name", ""), created=float(d.get("created", 0)))

    def new_id(self) -> int:
        ids = [r.id for r in self.all()]
        return max(ids, default=0) + 1

    def save(self, r: MyRecitation) -> MyRecitation:
        os.makedirs(self.root, exist_ok=True)
        if not r.created: r.created = time.time()
        d = {"title": r.title, "source": r.source, "audio": r.audio, "surah": r.surah, "ayahs": r.ayahs,
             "timings": [[t.ayah, t.start_ms, t.end_ms] for t in r.timings],
             "anchors": {str(k): v for k, v in r.anchors.items()}, "confident": r.confident,
             "reciter_name": r.reciter_name, "created": r.created}
        tmp = self._path(r.id) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self._path(r.id))
        return r

    def delete(self, rid: int) -> None:
        r = self.get(rid)
        for p in (self._path(rid), os.path.join(self.cache_dir, f"{rid}.npz")):
            if os.path.exists(p): os.unlink(p)
        if r and r.audio.startswith(self.media_dir) and os.path.exists(r.audio):
            others = [x for x in self.all() if x.audio == r.audio]
            if not others: os.unlink(r.audio)
