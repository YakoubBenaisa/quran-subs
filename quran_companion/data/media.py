"""Audio from what the user gives: a video link (YouTube and other sites, via yt-dlp), a direct
audio link, or a file on disk."""
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
from dataclasses import dataclass
from typing import Callable

from .. import system
from .http import CachedHttp

AUDIO_EXT = (".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".flac", ".webm", ".mp4", ".mka")
_PCT = re.compile(r"\[download\]\s+([\d.]+)%")


class MissingTool(RuntimeError):
    """yt-dlp is needed for video links."""


@dataclass(frozen=True)
class MediaInfo:
    source: str
    kind: str              # "video" | "url" | "file"
    title: str
    duration: float = 0.0  # s, 0 = unknown
    key: str = ""          # stable id for the downloaded file



def kind_of(src: str) -> str:
    s = src.strip()
    if os.path.exists(os.path.expanduser(s)): return "file"
    if re.match(r"https?://", s, re.I):
        path = urllib.parse.urlparse(s).path.lower()
        return "url" if path.endswith(AUDIO_EXT) else "video"
    raise ValueError("not a link or an existing file")


def _ytdlp() -> list[str]:
    if system.FROZEN: return system.self_command("yt-dlp")        # bundled: the app runs yt-dlp itself
    if importlib.util.find_spec("yt_dlp") is not None: return [sys.executable, "-m", "yt_dlp"]
    exe = shutil.which("yt-dlp") or (os.path.expanduser("~/.local/bin/yt-dlp") if os.path.exists(os.path.expanduser("~/.local/bin/yt-dlp")) else None)
    if exe: return [exe]
    raise MissingTool("yt-dlp is not installed (pip install --user yt-dlp)")


def _probe_title(path: str) -> tuple[str, float]:
    """(title - artist, duration s) from the file's tags; ffprobe if there is one, else ffmpeg's report."""
    try:
        probe = system.tool("ffprobe")
        if probe:
            out = subprocess.run([probe, "-v", "error", "-show_format", "-of", "json", path],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20, **system.no_window()).stdout
            fmt = json.loads(out).get("format", {})
            tags = {k.lower(): v for k, v in fmt.get("tags", {}).items()}
            dur = float(fmt.get("duration") or 0)
        else:
            ff = system.tool("ffmpeg")
            if not ff: return "", 0.0
            err = subprocess.run([ff, "-hide_banner", "-i", path], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20,
                                 **system.no_window()).stderr
            tags = {m.group(1).lower(): m.group(2).strip() for m in re.finditer(r"^\s{4}(\w+)\s*:\s(.*)$", err, re.M)}
            d = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", err)
            dur = int(d.group(1)) * 3600 + int(d.group(2)) * 60 + float(d.group(3)) if d else 0.0
        title = " - ".join(x for x in (tags.get("title", ""), tags.get("artist", "")) if x)
        return title, dur
    except (OSError, ValueError, subprocess.SubprocessError):
        return "", 0.0


class MediaFetcher:
    def __init__(self, media_dir: str, http: CachedHttp):
        self.dir, self.http = media_dir, http

    def info(self, src: str) -> MediaInfo:
        src = src.strip(); k = kind_of(src)
        if k == "file":
            path = os.path.abspath(os.path.expanduser(src))
            title, dur = _probe_title(path)
            return MediaInfo(path, k, title or os.path.splitext(os.path.basename(path))[0], dur, "")
        if k == "url":
            name = urllib.parse.unquote(os.path.basename(urllib.parse.urlparse(src).path))
            return MediaInfo(src, k, os.path.splitext(name)[0], 0.0, hashlib.sha1(src.encode()).hexdigest()[:12])
        out = subprocess.run(_ytdlp() + ["-J", "--no-playlist", "--no-warnings", src], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=90, **system.no_window())
        if out.returncode != 0:
            raise RuntimeError((out.stderr.strip().splitlines() or ["could not open the link"])[-1].replace("ERROR: ", ""))
        d = json.loads(out.stdout)
        key = re.sub(r"[^\w-]", "_", f"{d.get('extractor_key', 'web')}_{d.get('id', '')}")
        return MediaInfo(d.get("webpage_url") or src, k, d.get("title") or src, float(d.get("duration") or 0), key)

    def local_path(self, info: MediaInfo) -> str | None:
        """Already downloaded file for this media, if any."""
        if info.kind == "file": return info.source
        if not os.path.isdir(self.dir): return None
        for name in os.listdir(self.dir):
            if name.startswith(info.key + ".") and not name.endswith((".part", ".ytdl")): return os.path.join(self.dir, name)
        return None

    def fetch(self, info: MediaInfo, progress: Callable[[float], None] = lambda f: None,
              cancel: Callable[[], bool] = lambda: False) -> str:
        """Local audio file for the media (downloads once)."""
        have = self.local_path(info)
        if have: progress(1.0); return have
        os.makedirs(self.dir, exist_ok=True)
        if info.kind == "url":
            ext = os.path.splitext(urllib.parse.urlparse(info.source).path)[1] or ".mp3"
            dst = os.path.join(self.dir, info.key + ext)
            self.http.download(info.source, dst, lambda got, total: progress(got / total if total else 0), cancel)
            return dst
        cmd = _ytdlp() + ["-f", "bestaudio/best", "--no-playlist", "--no-warnings", "--newline", "--progress",
                          "-o", os.path.join(self.dir, info.key + ".%(ext)s"), "--print", "after_move:filepath", info.source]
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                             encoding="utf-8", errors="replace", **system.no_window())
        last = ""; path = ""
        assert p.stdout is not None
        for line in p.stdout:
            if cancel():
                p.kill(); p.wait(); raise InterruptedError("cancelled")
            m = _PCT.search(line)
            if m: progress(float(m.group(1)) / 100)
            elif line.strip().startswith(self.dir): path = line.strip()
            if line.strip(): last = line.strip()
        if p.wait() != 0 or not path or not os.path.exists(path):
            raise RuntimeError(last.replace("ERROR: ", "") or "download failed")
        return path
