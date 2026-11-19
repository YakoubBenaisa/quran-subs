"""HTTP with a disk cache: cached answers are reused, and served stale when offline."""
import json
import os
import time
import urllib.request
from typing import Any, Callable

UA = "Mozilla/5.0 (X11; Linux x86_64) quran-companion/5"
WEEK = 7 * 86400


class CachedHttp:
    def __init__(self, cache_dir: str, user_agent: str = UA, timeout: float = 30):
        self.cache_dir, self.ua, self.timeout = cache_dir, user_agent, timeout

    def fetch(self, url: str, timeout: float | None = None) -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": self.ua})
        with urllib.request.urlopen(req, timeout=timeout or self.timeout) as r:
            return r.read()

    def get_json(self, url: str, name: str, max_age: float | None = None) -> Any:
        """`name` is the cache file (relative path). max_age=None caches forever."""
        path = os.path.join(self.cache_dir, name)
        if os.path.exists(path) and (max_age is None or time.time() - os.path.getmtime(path) < max_age):
            try:
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, ValueError):
                pass
        try:
            data = json.loads(self.fetch(url))
        except Exception:
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            raise
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(path + ".tmp", path)
        return data

    def download(self, url: str, dst: str, progress: Callable[[int, int], None] | None = None,
                 cancel: Callable[[], bool] = lambda: False) -> None:
        """Download to `dst` via a .part file; raises InterruptedError when cancelled."""
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        tmp = dst + ".part"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": self.ua})
            with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
                total, got = int(r.headers.get("Content-Length") or 0), 0
                while True:
                    if cancel(): raise InterruptedError("cancelled")
                    b = r.read(1 << 16)
                    if not b: break
                    f.write(b); got += len(b)
                    if progress: progress(got, total)
            os.replace(tmp, dst)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)
