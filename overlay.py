#!/usr/bin/env python3
"""Quran floating overlay: outlined text only, click-through, always on top.

Modes
  recite    plays a whole surah; the text follows the reciter (mp3quran.net verse timings,
            plus quran.com word timings where available for exact page turns)
  memorize  silent; verses advance on their own (per word / fixed time / reciter's pace)
  manual    silent; advance with Super+Alt+→ (e.g. while a YouTube recitation plays)

Long verses are split into pages of at most N lines (default 3) at a fixed text size.

  quran-overlay.sh ui                  settings window
  quran-overlay.sh [--surah 18] [--ayah 1]     start the overlay
  quran-overlay.sh next|prev|pause|hide|bigger|smaller|nextsurah|prevsurah|toggle|quit
  quran-overlay.sh surah 36 [ayah]
"""
import argparse, bisect, json, locale, os, re, signal, socket, subprocess, sys, threading, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SOCK = os.environ.get("QOV_SOCK") or os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "quran-overlay.sock")
CFG = os.environ.get("QOV_CFG") or os.path.expanduser("~/.config/quran-overlay.json")
CACHE = os.path.expanduser("~/.cache/quran-overlay")
LIB = os.path.expanduser("~/.local/share/quran-overlay/audio")
LANG_DIR = os.path.join(HERE, "lang")
AQ = "https://api.alquran.cloud/v1"
MP3Q = "https://mp3quran.net/api/v3"
QDC = "https://api.qurancdn.com/api/qdc/audio/reciters"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) quran-overlay/3"}
WEEK = 7 * 86400
BASMALA = "بِسْمِ ٱللَّهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ"
ISTIADHA = "أَعُوذُ بِٱللَّهِ مِنَ ٱلشَّيْطَٰنِ ٱلرَّجِيمِ"
SADAQA = "صَدَقَ ٱللَّهُ ٱلْعَظِيمُ"
UI_FONT = "IBM Plex Sans Arabic"
OV_VERSION = 4  # bump when the overlay's command set changes, so the window can restart an outdated overlay
CMDS = {"next", "prev", "pause", "hide", "bigger", "smaller", "quit", "surah", "nextsurah", "prevsurah",
        "play", "restyle", "visible"}

DEFAULTS = dict(
    surah=1, ayah=1, range_from=1, range_to=0, loop=False, reciter=0, trans="", speed=1.0, volume=100,
    mode="recite", autonext=True, word_sync=True,
    mem_advance="words", mem_per_word=0.8, mem_min=3.0, mem_fixed=10.0, mem_gap=2.0, mem_repeat=1,
    mem_hint="none", hint_words=2, hint_delay=4.0,
    font="Amiri Quran", size=40, tr_font="Sans", tr_scale=45, color="#ffffff", outline="#000000",
    outline_w=4, bg=False, bg_color="#000000", bg_alpha=55, pos="bottom", margin=40,
    max_lines=3, max_width=80, tr_lines=2, ui_lang="auto", ui_font=UI_FONT, theme="system", visible=True)


# ---------------------------------------------------------------- config / IPC
_cfg_lock = threading.Lock()


def load_cfg():
    c = dict(DEFAULTS)
    try:
        with open(CFG) as f: c.update(json.load(f))
    except Exception:
        pass
    if not isinstance(c.get("reciter"), int): c["reciter"] = 0  # old versions stored "ar.alafasy"
    if "follow" in c:  # v2 setting
        if c.pop("follow"): c["mode"] = "manual"
    if c["mode"] not in ("recite", "memorize", "manual"): c["mode"] = "recite"
    return c


def update_cfg(**kw):
    with _cfg_lock:
        c = load_cfg(); c.update(kw)
        os.makedirs(os.path.dirname(CFG), exist_ok=True)
        with open(CFG + ".tmp", "w") as f: json.dump(c, f, ensure_ascii=False, indent=1)
        os.replace(CFG + ".tmp", CFG)
        return c


def send(cmd):
    try:
        s = socket.socket(socket.AF_UNIX); s.connect(SOCK); s.sendall(cmd.encode()); s.close(); return True
    except OSError:
        return False


def running():
    try:
        s = socket.socket(socket.AF_UNIX); s.connect(SOCK); s.close(); return True
    except OSError:
        return False


def overlay_pid():
    """PID of the process serving the overlay socket (None if not running)."""
    try:
        import struct
        s = socket.socket(socket.AF_UNIX); s.connect(SOCK)
        pid = struct.unpack("3i", s.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))[0]
        s.close(); return pid
    except OSError:
        return None


def overlay_current():
    c, pid = load_cfg(), overlay_pid()
    return bool(pid) and c.get("ov_pid") == pid and c.get("ov_version") == OV_VERSION


def restart_overlay(hidden=False):
    """Quit whatever overlay is running and start the current version (it resumes at the saved verse)."""
    send("quit")
    for _ in range(40):
        if not running(): break
        time.sleep(0.05)
    spawn_overlay(hidden)


def spawn_overlay(hidden=False):
    subprocess.Popen([sys.executable, os.path.abspath(__file__)] + (["--hidden"] if hidden else []), start_new_session=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ---------------------------------------------------------------- languages (lang/*.json)
_EN, _TR, LANG = {}, {}, {"code": "en", "dir": "ltr"}


def lang_list():
    out = []
    for fn in sorted(os.listdir(LANG_DIR)) if os.path.isdir(LANG_DIR) else []:
        if fn.endswith(".json"):
            try:
                with open(os.path.join(LANG_DIR, fn), encoding="utf-8") as f: d = json.load(f)
                out.append((fn[:-5], d.get("_name", fn[:-5]), d.get("_dir", "ltr")))
            except Exception:
                pass
    return out


def set_lang(code):
    if code in ("", "auto", None):
        sysl = (os.environ.get("LANG") or locale.getlocale()[0] or "en")[:2]
        code = sysl if os.path.exists(os.path.join(LANG_DIR, sysl + ".json")) else "en"

    def rd(c):
        try:
            with open(os.path.join(LANG_DIR, c + ".json"), encoding="utf-8") as f: return json.load(f)
        except Exception:
            return {}
    _EN.clear(); _EN.update(rd("en")); _TR.clear(); _TR.update(rd(code))
    LANG.update(code=code, dir=_TR.get("_dir", "ltr"))
    return code


def T(key, **kw):
    s = _TR.get(key) or _EN.get(key) or key
    try:
        return s.format(**kw) if kw else s
    except Exception:
        return s


def rtl():
    return LANG["dir"] == "rtl"


# ---------------------------------------------------------------- data (cached)
def fetch(url, timeout=30):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def get_json(url, name, max_age=None):
    path = os.path.join(CACHE, name)
    if os.path.exists(path) and (max_age is None or time.time() - os.path.getmtime(path) < max_age):
        try:
            with open(path, encoding="utf-8") as f: return json.load(f)
        except Exception:
            pass
    try:
        data = json.loads(fetch(url))
    except Exception:
        if os.path.exists(path):  # offline: use stale cache
            with open(path, encoding="utf-8") as f: return json.load(f)
        raise
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False)
    os.replace(path + ".tmp", path)
    return data


def bare(t):
    """Arabic letters only (no tashkeel / Quranic marks) for comparisons."""
    return re.sub("[ً-ٰٟۖ-ۭـ]", "", t)


def norm(t):
    """Tolerant matching: "husary" ~ "Al-Hussary", "alafasy" ~ "Alafasi", tashkeel ignored."""
    t = bare(t.casefold()).replace("ou", "u").replace("y", "i").replace("ee", "i").replace("oo", "u")
    t = re.sub(r"[^\w]", "", t.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا"))
    return re.sub(r"(.)\1+", r"\1", t)


def _skel(w):
    w = norm(w)
    if len(w) > 4 and (w.startswith("al") or w.startswith("el")): w = w[2:]
    if len(w) > 3 and w.startswith("ال"): w = w[2:]
    return (w[0] + re.sub("[aeiou]", "", w[1:])) if re.match("[a-z]", w) else w


def name_match(query, text):
    """'ahmed bin taleb' ~ 'Ahmad Talib bin Humaid', 'husary' ~ 'Al-Hussary', any word order."""
    qs = [_skel(x) for x in re.split(r"[\s\-'’·]+", query) if x.strip()]
    ts = [_skel(x) for x in re.split(r"[\s\-'’·]+", text) if x.strip()]
    whole = "".join(ts)
    return all(any(t.startswith(q) or (len(q) > 2 and q in t) for t in ts) or (len(q) > 3 and q in whole) for q in qs if q)


def ar_digits(n):
    return "".join("٠١٢٣٤٥٦٧٨٩"[int(d)] for d in str(n))


def tokens(text):
    """Display words of a verse; stand-alone pause marks (ۚ ۖ ۗ …) stick to the previous word,
    so word positions match quran.com word timings."""
    out = []
    for w in text.split(" "):
        if not w: continue
        if out and not re.search("[ء-يٱ-ۓ]", w): out[-1] += " " + w
        else: out.append(w)
    return out


def reciters():
    """Reciters that have whole-surah audio + verse timings on mp3quran.net."""
    reads = get_json(f"{MP3Q}/ayat_timing/reads", "reads.json", WEEK)
    try:
        eng = get_json(f"{MP3Q}/reciters?language=eng", "reciters_eng.json", WEEK)["reciters"]
    except Exception:
        eng = []
    info = {m["server"].rstrip("/"): (r["name"], m["name"]) for r in eng for m in r["moshaf"]}
    out = []
    for r in reads:
        en, style = info.get(r["folder_url"].rstrip("/"), ("", r.get("rewaya", "")))
        out.append(dict(id=r["id"], ar=r["name"], en=en, style=style, folder=r["folder_url"],
                        count=r.get("soar_count", 114)))
    out.sort(key=lambda r: (r["en"] or r["ar"]).lower())
    return out


def find_reciter(rid, recs=None):
    recs = recs or reciters()
    return (next((r for r in recs if r["id"] == rid), None)
            or next((r for r in recs if "afasy" in r["folder"]), None) or recs[0])


def surahs():
    return get_json(f"{AQ}/surah", "surahs.json")["data"]


def translations():
    return get_json(f"{AQ}/edition?format=text&type=translation", "translations.json", WEEK)["data"]


def slug(folder):
    return folder.rstrip("/").split("/audio/")[-1].replace("/", "_")


def local_audio(rec, s):
    return os.path.join(LIB, slug(rec["folder"]), f"{s:03d}.mp3")


def audio_src(rec, s):
    p = local_audio(rec, s)
    return p if os.path.exists(p) else rec["folder"] + f"{s:03d}.mp3"


def surah_text(s, trans=""):
    eds = "quran-uthmani" + (f",{trans}" if trans else "")
    data = get_json(f"{AQ}/surah/{s}/editions/{eds}", f"text/{s}_{trans or 'ar'}.json")["data"]
    ar, tr = data[0]["ayahs"], (data[1]["ayahs"] if trans else None)
    items = {}
    for i, a in enumerate(ar):
        t = a["text"].replace("﻿", "").strip()
        w = t.split(" ")
        if i == 0 and s not in (1, 9) and len(w) > 4 and bare(" ".join(w[:4])) == bare(BASMALA):
            t = " ".join(w[4:])  # basmala is shown separately (timing "ayah 0")
        items[a["numberInSurah"]] = dict(n=a["numberInSurah"], ar=t, tr=tr[i]["text"] if tr else "")
    return data[0]["englishName"], items


def load_timings(s, rec):
    tm = get_json(f"{MP3Q}/ayat_timing?surah={s}&read={rec['id']}", f"timing/{rec['id']}/{s}.json")
    times = []
    if isinstance(tm, list):
        times = sorted(((x["ayah"], x["start_time"], x["end_time"]) for x in tm), key=lambda t: t[1])
        if times and times[0][0] != 0 and times[0][1] > 1500:  # intro (basmala / isti'adha) before ayah 1
            times.insert(0, (0, 0, times[0][1]))
    return times


def load_surah(s, rec, trans, timing=True):
    name, items = surah_text(s, trans)
    return name, items, (load_timings(s, rec) if timing else [])


# quran.com has word-level timings for a few famous reciters. We use them as *relative* positions
# inside each verse (the recordings on mp3quran may differ slightly), to turn pages exactly.
QDC_KEYS = {7: ["afasi"], 3: ["sudais", "sudaes"], 4: ["shatri"], 5: ["rifai"], 6: ["husari"],
            10: ["shuraim", "shurim"], 9: ["minshawi", "menshawi"], 2: ["abdulbasit", "abdulbaset"],
            97: ["dosari", "dusari"], 161: ["tunaiji"]}
QDC_MUJAWWAD = {2: 1}
QDC_MUALLIM = {6: 12}


def qdc_id(rec):
    st = rec["style"].lower()
    if "hafs" not in st: return None
    n = norm(rec["en"] or "")
    for qid, keys in QDC_KEYS.items():
        if any(norm(k) in n for k in keys):
            if "jawwad" in st: return QDC_MUJAWWAD.get(qid)
            if "lim" in st or "allim" in st: return QDC_MUALLIM.get(qid)
            return qid
    return None


def word_fracs(s, rec):
    """{ayah: {word_pos(1-based): fraction of the verse duration}} or {} if not available."""
    qid = qdc_id(rec)
    if not qid: return {}
    d = get_json(f"{QDC}/{qid}/audio_files?chapter={s}&segments=true", f"qdc/{qid}/{s}.json")
    out = {}
    for v in d["audio_files"][0]["verse_timings"]:
        a, b = v["timestamp_from"], v["timestamp_to"]
        if b <= a: continue
        fr = {}
        for x in v.get("segments") or []:
            if len(x) == 3 and int(x[0]) not in fr: fr[int(x[0])] = max(0.0, (x[1] - a) / (b - a))
        if fr: out[int(v["verse_key"].split(":")[1])] = fr
    return out


def download_file(url, dst, cb=None, cancel=lambda: False):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + ".part"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r, open(tmp, "wb") as f:
            total, got = int(r.headers.get("Content-Length") or 0), 0
            while True:
                if cancel(): raise InterruptedError("cancelled")
                b = r.read(1 << 16)
                if not b: break
                f.write(b); got += len(b)
                if cb: cb(got, total)
        os.replace(tmp, dst)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


# ---------------------------------------------------------------- CLI dispatch (before importing Qt)
if __name__ == "__main__" and len(sys.argv) > 1:
    if sys.argv[1] == "toggle":
        if send("quit"): sys.exit(0)
        sys.argv.pop(1)
    elif sys.argv[1] in CMDS:
        if not send(" ".join(sys.argv[1:])): print("Overlay is not running."); sys.exit(1)
        sys.exit(0)

from PySide6.QtCore import (Qt, QTimer, Signal, QObject, QPointF, QRectF, QSize, QPropertyAnimation, QEasingCurve,
                            QEvent, QAbstractAnimation)
from PySide6.QtGui import (QPainter, QPainterPath, QPen, QColor, QFont, QFontMetricsF, QFontDatabase, QIcon,
                           QPixmap, QLinearGradient, QPalette)
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame,
                               QStackedWidget, QScrollArea, QButtonGroup, QComboBox, QSpinBox, QLineEdit,
                               QListWidget, QListWidgetItem, QCheckBox, QPushButton, QFontComboBox, QSlider,
                               QProgressBar, QLabel, QColorDialog, QCompleter, QMessageBox, QStyledItemDelegate,
                               QStyle, QSizePolicy, QGraphicsDropShadowEffect)


def register_fonts():
    """Bundled fonts. Returns the Quran font family."""
    for fn in sorted(os.listdir(os.path.join(HERE, "fonts"))):
        if fn.endswith((".ttf", ".otf")) and not fn.startswith("AmiriQuran"):
            QFontDatabase.addApplicationFont(os.path.join(HERE, "fonts", fn))
    fid = QFontDatabase.addApplicationFont(os.path.join(HERE, "fonts", "AmiriQuran.ttf"))
    fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
    return fams[0] if fams else "Noto Naskh Arabic"


class Bus(QObject):
    cmd = Signal(str)
    loaded = Signal(object)
    ended = Signal(int)
    data = Signal(object)
    dl = Signal(int, int, str)


# ---------------------------------------------------------------- pages: layout / painting (overlay + preview)
def make_font(kind, size, cfg, qfont):
    if kind == "ar":
        return QFont(cfg["font"] or qfont, max(6, int(size)))
    f = QFont(cfg["tr_font"] or "Sans", max(6, int(size * cfg["tr_scale"] / 100)))
    f.setWeight(QFont.DemiBold)
    return f


def wrap_tokens(toks, font, maxw):
    fm, lines, cur = QFontMetricsF(font), [], []
    for w in toks:
        if cur and fm.horizontalAdvance(" ".join(cur + [w])) > maxw: lines.append(cur); cur = [w]
        else: cur.append(w)
    if cur: lines.append(cur)
    return lines


def fit_translation(toks, cfg, qfont, maxw):
    if not toks: return [], None
    base = make_font("tr", cfg["size"], cfg, qfont); n = max(1, int(cfg["tr_lines"]))
    f = QFont(base)
    for scale in (1, 0.9, 0.8, 0.7):
        f.setPointSizeF(max(6.0, base.pointSizeF() * scale))
        lines = wrap_tokens(toks, f, maxw)
        if len(lines) <= n: return [" ".join(l) for l in lines], f
    lines = [" ".join(l) for l in lines[:n]]
    lines[-1] += " …"
    return lines, f


def paginate(ar, tr, cfg, qfont, maxw):
    """Split one verse into pages of at most `max_lines` Arabic lines, text size never shrinks.
    Pages are balanced (7 lines -> 3+2+2, never 3+3+1). Each page: lines, tr, trfont, w0 (first word
    index), frac (where the page starts, as a fraction of the verse, by letters)."""
    fa = make_font("ar", cfg["size"], cfg, qfont)
    toks = tokens(ar)
    lines = wrap_tokens(toks, fa, maxw) or [[]]
    ml = max(1, int(cfg["max_lines"]))
    P = -(-len(lines) // ml)
    if P > 1:  # re-wrap each page from its share of words so pages come out even
        base, extra = divmod(len(lines), P)
        groups, i = [], 0
        for k in range(P):
            n = base + (1 if k < extra else 0); groups.append(lines[i:i + n]); i += n
    else:
        groups = [lines]
    total = sum(len(t) for t in toks) or 1
    pages, w0, acc = [], 0, 0
    for g in groups:
        pages.append(dict(lines=[" ".join(l) for l in g], w0=w0, frac=acc / total))
        w0 += sum(len(l) for l in g); acc += sum(len(t) for l in g for t in l)
    trt = tr.split() if tr else []
    for k, pg in enumerate(pages):
        f1 = pages[k + 1]["frac"] if k + 1 < len(pages) else 1.0
        part = trt[round(pg["frac"] * len(trt)):round(f1 * len(trt))]
        if k + 1 < len(pages):
            pg["lines"][-1] += " …"
            if part: part = part + ["…"]
        pg["tr"], pg["trfont"] = fit_translation(part, cfg, qfont, maxw)
    return pages


def message_page(text, kind, cfg, qfont, maxw):
    f = make_font(kind, cfg["size"], cfg, qfont)
    lines = [" ".join(l) for l in wrap_tokens(text.split(), f, maxw)]
    return dict(lines=lines, tr=[], trfont=None) if kind == "ar" else dict(lines=[], tr=lines, trfont=f)


def page_lines(page, cfg, qfont):
    out, h = [], 0
    fa = make_font("ar", cfg["size"], cfg, qfont)
    ft = page.get("trfont") or make_font("tr", cfg["size"], cfg, qfont)
    for kind, lines, f in (("ar", page.get("lines", []), fa), ("tr", page.get("tr", []), ft)):
        fm = QFontMetricsF(f)
        for ln in lines:
            lh = fm.height() * (1.25 if kind == "ar" else 1.1)
            out.append((ln, f, lh, fm.horizontalAdvance(ln))); h += lh
    return out, h


def paint_lines(p, width, height, lines, cfg):
    p.setRenderHint(QPainter.Antialiasing)
    if cfg["bg"] and lines:
        w = max(l[3] for l in lines) + 60
        col = QColor(cfg["bg_color"]); col.setAlpha(int(cfg["bg_alpha"] * 2.55))
        p.setPen(Qt.NoPen); p.setBrush(col)
        p.drawRoundedRect(QRectF((width - w) / 2, 4, w, height - 8), 16, 16)
    oc = QColor(cfg["outline"]); oc.setAlpha(230)
    y = 15
    for text, f, lh, tw in lines:
        fm = QFontMetricsF(f)
        path = QPainterPath()
        path.addText(QPointF((width - tw) / 2, y + fm.ascent() + (lh - fm.height()) / 2), f, text)
        if cfg["outline_w"] > 0:
            pw = max(1.0, cfg["outline_w"] * f.pointSizeF() / 40)
            p.strokePath(path, QPen(oc, pw, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.fillPath(path, QColor(cfg["color"]))
        y += lh


# ---------------------------------------------------------------- overlay
class Overlay(QWidget):
    def __init__(self):
        super().__init__()
        self.bus = Bus()
        self.cfg = load_cfg(); set_lang(self.cfg["ui_lang"])
        self.items, self.times, self.starts, self.tmap, self.fracs, self.pcache = {}, [], [], {}, {}, {}
        self.cur, self.page, self.view = None, 0, None
        self.rec, self.surah, self.proc, self.paused, self.gen, self.lgen = None, 1, None, False, 0, 0
        self.clock, self.hidden, self.lines, self.mem, self.rng = None, False, [], None, (1, 0)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                            | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus
                            | Qt.X11BypassWindowManagerHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.qfont = register_fonts()
        self.bus.cmd.connect(self.on_cmd)
        self.bus.loaded.connect(self.on_loaded)
        self.bus.ended.connect(self.on_ended)
        self.timer = QTimer(self); self.timer.timeout.connect(self.tick); self.timer.start(100)
        self.start_server()
        self.rng = (self.cfg["range_from"], self.cfg["range_to"])
        self.hidden = "--hidden" in sys.argv
        update_cfg(visible=not self.hidden, ov_pid=os.getpid(), ov_version=OV_VERSION)
        self.load(self.cfg["surah"], self.cfg["ayah"])

    def maxw(self):
        return QApplication.primaryScreen().availableGeometry().width() * self.cfg["max_width"] / 100

    # ---------- loading ----------
    def load(self, s, ayah=1):
        self.stop_audio(); self.mem = None
        self.cfg = c = load_cfg()
        self.surah, self.cur, self.page = s, None, 0
        self.lgen += 1; lg = self.lgen
        self.message(T("ov_loading"), "tr")

        def work():
            try:
                rec = find_reciter(c["reciter"])
                _, items = surah_text(s, c["trans"])
                times, fr = [], {}
                if c["mode"] != "manual":
                    try:
                        times = load_timings(s, rec)
                    except Exception:
                        if c["mode"] == "recite": raise
                if c["mode"] == "recite" and c["word_sync"]:
                    try: fr = word_fracs(s, rec)
                    except Exception: fr = {}
                self.bus.loaded.emit((lg, s, ayah, rec, items, times, fr))
            except Exception as e:
                self.bus.loaded.emit((lg, f"{type(e).__name__}: {e}"))
        threading.Thread(target=work, daemon=True).start()

    def on_loaded(self, res):
        if res[0] != self.lgen: return
        if len(res) == 2:
            self.message(T("ov_failed", err=res[1]), "tr"); return
        _, s, ayah, self.rec, self.items, self.times, self.fracs = res
        self.starts = [t[1] for t in self.times]
        self.tmap = {t[0]: (t[1], t[2]) for t in self.times}
        self.pcache = {}
        ayah = max(1, min(ayah, len(self.items)))
        mode = self.cfg["mode"]
        if mode == "recite":
            if not self.times:
                self.message(T("ov_no_timing", s=s), "tr"); return
            start = self.tmap.get(ayah, (0, 0))[0] if ayah > 1 else 0
            self.play_from(start / 1000)
        elif mode == "memorize":
            self.mem_start(ayah, rep=1)
        else:
            self.show_page(ayah, 0)

    def range_end(self):
        a, b = self.rng
        return b if b and b >= a else 0

    # ---------- pages ----------
    def pages_for(self, n):
        if n in self.pcache: return self.pcache[n]
        if n == 0:
            pages = paginate(ISTIADHA if self.surah in (1, 9) else BASMALA, "", self.cfg, self.qfont, self.maxw())
        else:
            a = self.items[n]
            pages = paginate(a["ar"] + " ﴿" + ar_digits(n) + "﴾", a["tr"], self.cfg, self.qfont, self.maxw())
            fr = self.fracs.get(n)
            if fr:  # exact page turns from word timings
                for pg in pages[1:]:
                    if pg["w0"] + 1 in fr: pg["frac"] = fr[pg["w0"] + 1]
        self.pcache[n] = pages
        return pages

    def show_page(self, n, k):
        if n not in self.items and n != 0: return
        pages = self.pages_for(n)
        k = max(0, min(k, len(pages) - 1))
        changed = n != self.cur
        self.cur, self.page, self.view = n, k, ("page", n, k)
        self.render(pages[k])
        if changed and n > 0: update_cfg(surah=self.surah, ayah=n)

    def message(self, text, kind="tr"):
        self.view = ("msg", text, kind)
        self.render(message_page(text, kind, self.cfg, self.qfont, self.maxw()))

    def redraw(self):
        self.pcache = {}
        v = self.view
        if not v: return
        if v[0] == "page": self.show_page(v[1], v[2])
        elif v[0] == "msg": self.message(v[1], v[2])
        elif v[0] == "hint": self.show_hint(v[1])
        elif v[0] == "blank": self.render(dict(lines=[], tr=[]))

    def render(self, page):
        self.lines, h = page_lines(page, self.cfg, self.qfont)
        scr = QApplication.primaryScreen().availableGeometry()
        h = int(h + 30)
        m = int(self.cfg["margin"])
        y = scr.top() + m if self.cfg["pos"] == "top" else scr.bottom() - h - m
        self.setGeometry(scr.left(), y, scr.width(), h)
        if not self.hidden: self.show_window()
        self.update()

    def show_window(self):
        QWidget.show(self); self.raise_()

    def show_hint(self, n):
        toks = tokens(self.items[n]["ar"])
        k = max(1, int(self.cfg["hint_words"]))
        self.view = ("hint", n)
        self.render(dict(lines=[" ".join(toks[:k]) + (" …" if len(toks) > k else "")], tr=[]))

    # ---------- recite: one ffplay per surah; its clock drives the text ----------
    def play_from(self, sec):
        self.stop_audio()
        c = self.cfg
        self.gen += 1; g = self.gen
        cmd = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "error", "-stats",
               "-volume", str(int(c["volume"]))]
        if sec > 0: cmd += ["-ss", f"{sec:.2f}"]
        if abs(float(c["speed"]) - 1) > 0.01: cmd += ["-af", f"atempo={float(c['speed']):.2f}"]
        cmd.append(audio_src(self.rec, self.surah))
        self.clock = sec
        p = self.proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                         stderr=subprocess.PIPE)

        def reader():
            buf = b""
            while True:
                b = p.stderr.read1(512)
                if not b: break
                parts = re.split(rb"[\r\n]", buf + b); buf = parts.pop()
                for ln in parts:
                    m = re.match(rb"\s*(\d+\.\d+)", ln)
                    if m and g == self.gen: self.clock = float(m.group(1))
            p.wait(); self.bus.ended.emit(g)
        threading.Thread(target=reader, daemon=True).start()
        self.tick()

    def stop_audio(self):
        self.gen += 1
        if self.proc and self.proc.poll() is None:
            if self.paused: self.proc.send_signal(signal.SIGCONT)
            self.proc.terminate()
        self.proc, self.paused = None, False

    def tick(self):
        if self.paused: return
        if self.cfg["mode"] == "memorize":
            if self.mem and time.monotonic() >= self.mem["end"]: self.mem_step()
            return
        if not self.proc or self.clock is None or not self.times: return
        ms = self.clock * 1000
        i = max(0, bisect.bisect_right(self.starts, ms) - 1)
        n, st, en = self.times[i]
        end = self.range_end()
        if end and n > end:
            if self.cfg["loop"]:
                self.play_from(self.tmap.get(self.rng[0], (0, 0))[0] / 1000)
            else:
                self.stop_audio(); self.message(SADAQA, "ar")
            return
        pages = self.pages_for(n) if (n in self.items or n == 0) else [dict(frac=0)]
        frac = (ms - st) / max(1, en - st)
        k = max([j for j, pg in enumerate(pages) if pg["frac"] <= frac] or [0])
        if (n, k) != (self.cur, self.page) or (self.view and self.view[0] != "page"): self.show_page(n, k)

    def on_ended(self, g):
        if g != self.gen: return
        self.proc = None
        finished = self.times and (self.clock or 0) * 1000 >= self.times[-1][1] - 1000
        if not finished:
            self.message(T("ov_stopped"), "tr"); return
        self.next_surah_or_finish()

    def next_surah_or_finish(self):
        if self.cfg["autonext"] and self.surah < 114 and not self.range_end():
            self.rng = (1, 0); update_cfg(range_from=1, range_to=0); self.load(self.surah + 1, 1)
        else:
            self.message(SADAQA, "ar")

    # ---------- memorize: silent, self-timed ----------
    def verse_seconds(self, n):
        c = self.cfg
        if c["mem_advance"] == "fixed": return float(c["mem_fixed"])
        if c["mem_advance"] == "reciter" and n in self.tmap:
            st, en = self.tmap[n]
            return max(1.5, (en - st) / 1000 / max(0.5, float(c["speed"])))
        return max(float(c["mem_min"]), len(tokens(self.items[n]["ar"])) * float(c["mem_per_word"]))

    def mem_start(self, n, rep=1):
        c = self.cfg
        pages, D = self.pages_for(n), self.verse_seconds(n)
        steps = []
        if c["mem_hint"] == "reveal": steps.append((("hint",), float(c["hint_delay"])))
        for k, pg in enumerate(pages):
            f1 = pages[k + 1]["frac"] if k + 1 < len(pages) else 1.0
            steps.append((("page", k), max(1.0, D * (f1 - pg["frac"]))))
        if c["mem_hint"] == "fade": steps.append((("blank",), D))
        if float(c["mem_gap"]) > 0:
            steps.append((("blank",) if c["mem_hint"] == "fade" else ("page", len(pages) - 1), float(c["mem_gap"])))
        self.mem = dict(n=n, rep=rep, steps=steps, i=-1, end=0, left=0)
        self.mem_step()

    def mem_step(self):
        m = self.mem
        m["i"] += 1
        if m["i"] >= len(m["steps"]):  # verse done
            n = m["n"]
            if m["rep"] < int(self.cfg["mem_repeat"]): self.mem_start(n, m["rep"] + 1); return
            end = self.range_end()
            if (end and n >= end) or n >= len(self.items):
                if end and self.cfg["loop"]: self.mem_start(self.rng[0]); return
                self.mem = None
                if n >= len(self.items) and not end: self.next_surah_or_finish()
                else: self.message(SADAQA, "ar")
                return
            self.mem_start(n + 1); return
        what, dur = m["steps"][m["i"]]
        m["end"] = time.monotonic() + dur
        if what[0] == "page": self.show_page(m["n"], what[1])
        elif what[0] == "hint": self.cur = m["n"]; self.show_hint(m["n"]); update_cfg(surah=self.surah, ayah=m["n"])
        else: self.view = ("blank",); self.render(dict(lines=[], tr=[]))

    # ---------- commands ----------
    def step(self, d):
        if not self.items: return
        mode, n = self.cfg["mode"], self.cur or 0
        if mode == "manual":  # pages first, then verses
            pages = self.pages_for(n) if n else [None]
            if d > 0 and n and self.page + 1 < len(pages): self.show_page(n, self.page + 1)
            elif d < 0 and n and self.page > 0: self.show_page(n, self.page - 1)
            else:
                m = max(1, min(n + d, len(self.items)))
                self.show_page(m, 0 if d >= 0 or m == n else len(self.pages_for(m)) - 1)
        elif mode == "memorize":
            self.mem_start(max(1, min(n + d, len(self.items))))
        else:
            t = self.tmap.get(n + d)
            if t: self.play_from(t[0] / 1000)

    def toggle_pause(self):
        mode = self.cfg["mode"]
        if mode == "recite":
            if self.proc and self.proc.poll() is None:
                self.proc.send_signal(signal.SIGCONT if self.paused else signal.SIGSTOP)
                self.paused = not self.paused
            elif self.times:
                self.step(0)
        elif mode == "memorize" and self.mem:
            if self.paused: self.mem["end"] = time.monotonic() + self.mem["left"]
            else: self.mem["left"] = max(0, self.mem["end"] - time.monotonic())
            self.paused = not self.paused

    def on_cmd(self, c):
        p = c.split()
        k = p[0] if p else ""
        if k in ("next", "prev"):
            self.step(1 if k == "next" else -1)
        elif k == "pause":
            self.toggle_pause()
        elif k == "hide":
            self.set_visible(self.hidden)
        elif k == "visible" and len(p) > 1:
            self.set_visible(p[1] == "1")
        elif k in ("bigger", "smaller"):
            self.cfg = update_cfg(size=max(16, self.cfg["size"] + (4 if k == "bigger" else -4))); self.redraw()
        elif k == "surah" and len(p) > 1 and p[1].isdigit():
            self.rng = (1, 0); self.load(max(1, min(114, int(p[1]))), int(p[2]) if len(p) > 2 and p[2].isdigit() else 1)
        elif k in ("nextsurah", "prevsurah"):
            self.rng = (1, 0); self.load(max(1, min(114, self.surah + (1 if k == "nextsurah" else -1))), 1)
        elif k == "play":
            c = load_cfg(); self.rng = (c["range_from"], c["range_to"]); self.load(c["surah"], c["ayah"])
        elif k == "restyle":
            self.cfg = load_cfg(); self.redraw()
        elif k == "quit":
            QApplication.quit()

    def set_visible(self, on):
        """Show or hide the verses on screen; the recitation keeps going."""
        self.hidden = not on; self.setVisible(on)
        if on: self.redraw()
        update_cfg(visible=on)

    def start_server(self):
        try: os.unlink(SOCK)
        except FileNotFoundError: pass
        srv = socket.socket(socket.AF_UNIX); srv.bind(SOCK); srv.listen(4)

        def loop():
            while True:
                c, _ = srv.accept()
                self.bus.cmd.emit(c.recv(256).decode(errors="ignore")); c.close()
        threading.Thread(target=loop, daemon=True).start()

    def paintEvent(self, _):
        p = QPainter(self); paint_lines(p, self.width(), self.height(), self.lines, self.cfg); p.end()


# ---------------------------------------------------------------- settings window: theme (dark / light)
THEMES = {
    "dark": dict(BG="#0b0d10", SIDE="#101419", CARD="#151a20", CARD2="#1a2027", FIELD="#1d232b", BORDER="#252c35",
                 TEXT="#e8ebef", MUTED="#8b94a3", SUB="#b2b9c3", ACCENT="#10b981", ACCENT2="#34d399", ACCENT3="#047857",
                 ON="#03130d", HOVER="#1b2129", BTN="#1f252e", BTNH="#272e38", SCROLL="#2b323c", KNOB="#8b94a3",
                 TRACK="#262c35", GLOW=90, BLOB=30),
    "light": dict(BG="#f2f5f4", SIDE="#ffffff", CARD="#ffffff", CARD2="#fbfdfc", FIELD="#f1f4f3", BORDER="#dfe6e3",
                  TEXT="#111827", MUTED="#6b7280", SUB="#4b5563", ACCENT="#059669", ACCENT2="#10b981", ACCENT3="#047857",
                  ON="#ffffff", HOVER="#edf3f0", BTN="#ffffff", BTNH="#f1f5f3", SCROLL="#cbd5d1", KNOB="#ffffff",
                  TRACK="#d5ddda", GLOW=60, BLOB=34),
}
C = dict(THEMES["dark"], name="dark")


def system_dark():
    try:
        cs = QApplication.styleHints().colorScheme()
        if cs == Qt.ColorScheme.Dark: return True
        if cs == Qt.ColorScheme.Light: return False
    except Exception:
        pass
    try:  # GNOME fallback
        out = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                             capture_output=True, text=True, timeout=2).stdout
        return "dark" in out
    except Exception:
        return True


def theme_name(cfg):
    t = cfg.get("theme", "system")
    if t not in THEMES: t = "dark" if system_dark() else "light"
    return t


def rgba(hexc, a):
    q = QColor(hexc); return f"rgba({q.red()},{q.green()},{q.blue()},{a})"


# 24x24 icons. LINE = stroked, FILL = solid. Media/arrow icons are mirrored for right-to-left.
LINE = {
    "book": '<path d="M2 4.5h6a4 4 0 0 1 4 4V20a3 3 0 0 0-3-3H2z"/><path d="M22 4.5h-6a4 4 0 0 0-4 4V20a3 3 0 0 1 3-3h7z"/>',
    "palette": '<path d="M12 22a10 10 0 1 1 10-10c0 2.8-2.2 4-4 4h-1.8a2 2 0 0 0-1.5 3.3A1.7 1.7 0 0 1 12 22z"/>'
               '<circle cx="7.5" cy="11" r="1.1"/><circle cx="10.5" cy="7" r="1.1"/><circle cx="15.5" cy="7.5" r="1.1"/>',
    "download": '<path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    "moon": '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
    "auto": '<rect x="2" y="3.5" width="20" height="13.5" rx="2.5"/><path d="M8 21h8M12 17v4"/>',
    "globe": '<circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15 15 0 0 1 0 20a15 15 0 0 1 0-20z"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "trash": '<path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14"/>',
    "keyboard": '<rect x="2" y="6" width="20" height="12" rx="2.5"/><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7 14h10"/>',
    "reset": '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/>',
    "x": '<path d="M18 6 6 18M6 6l12 12"/>',
    "cloud": '<path d="M7 18a5 5 0 1 1 .9-9.9A6 6 0 0 1 19.5 10 4 4 0 0 1 18 18z"/><path d="M12 11v6M9.5 14.5 12 17l2.5-2.5"/>',
    "star8": '<rect x="6" y="6" width="12" height="12" rx="1"/><rect x="6" y="6" width="12" height="12" rx="1" transform="rotate(45 12 12)"/><circle cx="12" cy="12" r="2.2"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
}
FILL = {
    "play": '<path d="M8 5.6v12.8a1.1 1.1 0 0 0 1.7.9l10-6.4a1.1 1.1 0 0 0 0-1.8l-10-6.4A1.1 1.1 0 0 0 8 5.6z"/>',
    "pause": '<rect x="6" y="5" width="4.2" height="14" rx="1.3"/><rect x="13.8" y="5" width="4.2" height="14" rx="1.3"/>',
    "prev": '<path d="M18.5 6.3v11.4a1.1 1.1 0 0 1-1.8.9L9.4 13a1.2 1.2 0 0 1 0-2l7.3-5.6a1.1 1.1 0 0 1 1.8.9z"/><rect x="5" y="5" width="2.8" height="14" rx="1.3"/>',
    "next": '<path d="M5.5 6.3v11.4a1.1 1.1 0 0 0 1.8.9l7.3-5.6a1.2 1.2 0 0 0 0-2L7.3 5.4a1.1 1.1 0 0 0-1.8.9z"/><rect x="16.2" y="5" width="2.8" height="14" rx="1.3"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="2.6"/>',
}
MIRROR = {"prev", "next", "reset"}
SW_ICONS = {
    "off": "<svg xmlns='http://www.w3.org/2000/svg' width='40' height='24' viewBox='0 0 40 24'><rect x='1' y='2' width='38' height='20' rx='10' fill='{TRACK}'/><circle cx='12' cy='12' r='7.5' fill='{KNOB}'/></svg>",
    "on": "<svg xmlns='http://www.w3.org/2000/svg' width='40' height='24' viewBox='0 0 40 24'><defs><linearGradient id='g' x1='0' y1='0' x2='0' y2='1'><stop offset='0' stop-color='{ACCENT2}'/><stop offset='1' stop-color='{ACCENT}'/></linearGradient></defs><rect x='1' y='2' width='38' height='20' rx='10' fill='url(#g)'/><circle cx='28' cy='12' r='7.5' fill='#ffffff'/></svg>",
    "down": "<svg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'><path d='M2.5 4.5 6 8l3.5-3.5' fill='none' stroke='{MUTED}' stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round'/></svg>",
    "up": "<svg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'><path d='M2.5 7.5 6 4l3.5 3.5' fill='none' stroke='{MUTED}' stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round'/></svg>",
}
_ICON_CACHE = {}


def _icon_dir():
    d = os.path.join(CACHE, "ui-icons", C["name"]); os.makedirs(d, exist_ok=True); return d


def _write(name, svg):
    p = os.path.join(_icon_dir(), name + ".svg")
    with open(p, "w") as f: f.write(svg)
    return p


def svg_icon(name, color=None, mirror=None):
    color = color or C["TEXT"]
    mirror = (name in MIRROR and rtl()) if mirror is None else mirror
    body = LINE.get(name) or FILL[name]
    if mirror: body = f'<g transform="translate(24 0) scale(-1 1)">{body}</g>'
    paint = (f'fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"'
             if name in LINE else f'fill="{color}"')
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" {paint}>{body}</svg>'


def icon(name, color=None, mirror=None):
    key = (C["name"], name, color, mirror, rtl())
    if key not in _ICON_CACHE:
        m = (name in MIRROR and rtl()) if mirror is None else mirror
        p = _write(f"{name}-{(color or C['TEXT']).strip('#')}-{'m' if m else 'n'}", svg_icon(name, color, mirror))
        _ICON_CACHE[key] = QIcon(p)
    return _ICON_CACHE[key]


def tile_svg(name, top, bottom, fg="#ffffff", glyph_opacity=1.0):
    """A glossy rounded tile with a line icon: gradient body, top highlight, soft drop shadow."""
    body = LINE[name]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80" viewBox="0 0 40 40">
<defs><linearGradient id="b" x1="0" y1="0" x2="0.4" y2="1"><stop offset="0" stop-color="{top}"/><stop offset="1" stop-color="{bottom}"/></linearGradient>
<linearGradient id="h" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffffff" stop-opacity="0.42"/><stop offset="1" stop-color="#ffffff" stop-opacity="0"/></linearGradient></defs>
<rect x="3" y="4.5" width="34" height="34" rx="10" fill="#000000" opacity="0.22"/>
<rect x="3" y="2" width="34" height="34" rx="10" fill="url(#b)"/>
<rect x="4.2" y="3" width="31.6" height="15" rx="8.5" fill="url(#h)"/>
<g transform="translate(9.2 8.2) scale(0.9)" fill="none" stroke="{fg}" stroke-opacity="{glyph_opacity}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">{body}</g></svg>'''


def tile_icon(name, active=None):
    """QIcon with an inactive (muted) tile and an active (accent) tile for checked buttons."""
    key = ("tile", C["name"], name, active)
    if key not in _ICON_CACHE:
        on = _write(f"tile-{name}-on", tile_svg(name, C["ACCENT2"], C["ACCENT3"]))
        off = _write(f"tile-{name}-off", tile_svg(name, "#3a424d" if C["name"] == "dark" else "#e4ebe8",
                                                  "#262c35" if C["name"] == "dark" else "#cfd9d5",
                                                  "#ffffff" if C["name"] == "dark" else "#4b5563", 0.85))
        ic = QIcon()
        if active is None:
            ic.addFile(off, QSize(), QIcon.Normal, QIcon.Off); ic.addFile(on, QSize(), QIcon.Normal, QIcon.On)
        else:
            ic.addFile(on if active else off)
        _ICON_CACHE[key] = ic
    return _ICON_CACHE[key]


def make_icons():
    out = {}
    for k, v in SW_ICONS.items():
        svg = v.format(**C)
        if rtl() and k in ("on", "off"):  # knob sits on the other side in right-to-left
            svg = svg.replace("cx='12'", "cx='@'").replace("cx='28'", "cx='12'").replace("cx='@'", "cx='28'")
        out[k] = _write(k + ("-rtl" if rtl() else ""), svg)
    return out


def build_qss(i):
    c = C
    fill, rest = ("add", "sub") if rtl() else ("sub", "add")  # Qt does not mirror slider pages in RTL
    return f"""
QWidget {{ color:{c['TEXT']}; }}
QStackedWidget, QScrollArea, QWidget#page, QWidget#modeopts {{ background:transparent; }}
QScrollArea {{ border:none; }}
QFrame#side {{ background:{c['SIDE']}; border:none; }}
QFrame#bar {{ background:{c['SIDE']}; border-top:1px solid {c['BORDER']}; }}
QLabel#brandAr {{ color:{c['ACCENT']}; font-size:15pt; font-weight:700; }}
QLabel#quran {{ color:{c['ACCENT']}; }}
QLabel#brand {{ font-size:12.5pt; font-weight:700; }}
QLabel#muted {{ color:{c['MUTED']}; }}
QLabel#small {{ color:{c['MUTED']}; font-size:9pt; }}
QLabel#h1 {{ font-size:20pt; font-weight:700; }}
QLabel#h2 {{ font-size:11.5pt; font-weight:700; }}
QLabel#field {{ color:{c['MUTED']}; font-size:8.5pt; font-weight:700; letter-spacing:0.6px; }}
QLabel#value {{ color:{c['ACCENT']}; font-weight:700; }}
QLabel#bigname {{ font-size:16pt; font-weight:700; }}
QLabel#npname {{ color:{c['ACCENT']}; font-size:12.5pt; font-weight:700; }}
QLabel#stat {{ font-size:22pt; font-weight:800; color:{c['ACCENT']}; }}
QLabel#kbd {{ background:{c['FIELD']}; border:1px solid {c['BORDER']}; border-bottom:2px solid {c['BORDER']};
             border-radius:6px; padding:1px 6px; font-size:8.5pt; font-weight:700; color:{c['SUB']}; }}
QLabel#modedesc {{ color:{c['SUB']}; background:{rgba(c['ACCENT'], 0.08)}; border:1px solid {rgba(c['ACCENT'], 0.18)};
                   border-radius:10px; padding:10px 12px; }}
QFrame#card {{ background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {c['CARD2']}, stop:1 {c['CARD']});
              border:1px solid {c['BORDER']}; border-radius:18px; }}
QFrame#shortcuts {{ background:{c['CARD']}; border:1px solid {c['BORDER']}; border-radius:14px; }}
QPushButton#nav {{ text-align:left; padding:7px 10px; border:none; border-radius:12px; background:transparent;
                   color:{c['MUTED']}; font-weight:600; font-size:10.5pt; }}
QPushButton#nav:hover {{ background:{c['HOVER']}; color:{c['TEXT']}; }}
QPushButton#nav:checked {{ background:{rgba(c['ACCENT'], 0.12)}; color:{c['ACCENT']}; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QFontComboBox {{ background:{c['FIELD']}; border:1px solid {c['BORDER']};
        border-radius:10px; padding:7px 10px; selection-background-color:{c['ACCENT']}; selection-color:{c['ON']}; min-height:20px; }}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QFontComboBox:hover {{ border-color:{rgba(c['ACCENT'], 0.45)}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QFontComboBox:focus {{ border:1px solid {c['ACCENT']}; }}
QComboBox::drop-down {{ border:none; width:28px; }}
QComboBox::down-arrow {{ image:url({i['down']}); width:12px; height:12px; }}
QComboBox QAbstractItemView {{ background:{c['CARD']}; border:1px solid {c['BORDER']}; selection-background-color:{c['ACCENT']};
        selection-color:{c['ON']}; outline:0; padding:4px; border-radius:10px; }}
QSpinBox::up-button, QSpinBox::down-button {{ width:20px; border:none; background:transparent; }}
QSpinBox::up-arrow {{ image:url({i['up']}); width:10px; height:10px; }}
QSpinBox::down-arrow {{ image:url({i['down']}); width:10px; height:10px; }}
QListWidget {{ background:transparent; border:none; outline:0; }}
QListWidget#lib::item {{ padding:10px; border-radius:10px; margin:1px 0; }}
QListWidget#lib::item:hover {{ background:{c['HOVER']}; }}
QListWidget#lib::item:selected {{ background:{rgba(c['ACCENT'], 0.14)}; color:{c['TEXT']}; }}
QPushButton {{ background:{c['BTN']}; border:1px solid {c['BORDER']}; border-radius:10px; padding:8px 14px; font-weight:600; }}
QPushButton:hover {{ background:{c['BTNH']}; border-color:{rgba(c['ACCENT'], 0.35)}; }}
QPushButton:pressed {{ background:{c['HOVER']}; }}
QPushButton:disabled {{ color:{c['MUTED']}; background:{c['FIELD']}; border-color:{c['BORDER']}; }}
QPushButton#primary {{ background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {c['ACCENT2']}, stop:1 {c['ACCENT']});
        color:{c['ON']}; border:1px solid {c['ACCENT3']}; padding:12px 22px; font-size:11pt; font-weight:700; border-radius:12px; }}
QPushButton#primary:hover {{ background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #5ee0b0, stop:1 {c['ACCENT2']}); }}
QPushButton#primary:disabled {{ background:{rgba(c['ACCENT'], 0.35)}; color:{c['ON']}; border-color:transparent; }}
QPushButton#danger {{ color:#ef4444; }}
QPushButton#round {{ border-radius:21px; min-width:42px; max-width:42px; min-height:42px; max-height:42px; padding:0; }}
QPushButton#roundMain {{ border-radius:27px; min-width:54px; max-width:54px; min-height:54px; max-height:54px; padding:0;
        background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {c['ACCENT2']}, stop:1 {c['ACCENT3']}); border:none; }}
QPushButton#roundMain:hover {{ background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #5ee0b0, stop:1 {c['ACCENT']}); }}
QPushButton#seg {{ border-radius:0; padding:8px 14px; background:{c['FIELD']}; }}
QPushButton#seg[first="true"] {{ border-top-left-radius:10px; border-bottom-left-radius:10px; }}
QPushButton#seg[last="true"] {{ border-top-right-radius:10px; border-bottom-right-radius:10px; }}
QPushButton#seg:checked {{ background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {c['ACCENT2']}, stop:1 {c['ACCENT']});
        color:{c['ON']}; border-color:{c['ACCENT']}; }}
QPushButton#iconseg {{ border-radius:0; padding:7px; background:{c['FIELD']}; }}
QPushButton#iconseg[first="true"] {{ border-top-left-radius:10px; border-bottom-left-radius:10px; }}
QPushButton#iconseg[last="true"] {{ border-top-right-radius:10px; border-bottom-right-radius:10px; }}
QPushButton#iconseg:checked {{ background:{rgba(c['ACCENT'], 0.16)}; border-color:{c['ACCENT']}; }}
QCheckBox {{ spacing:12px; font-weight:600; }}
QCheckBox::indicator {{ width:40px; height:24px; image:url({i['off']}); }}
QCheckBox::indicator:checked {{ image:url({i['on']}); }}
QSlider {{ min-height:24px; }}
QSlider::groove:horizontal {{ height:8px; background:{c['TRACK']}; border-radius:4px; }}
QSlider::{fill}-page:horizontal {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {c['ACCENT2'] if rtl() else c['ACCENT3']}, stop:1 {c['ACCENT3'] if rtl() else c['ACCENT2']}); border-radius:4px; }}
QSlider::{rest}-page:horizontal {{ background:{c['TRACK']}; border-radius:4px; }}
QSlider::handle:horizontal {{ background:#ffffff; border:4px solid {c['ACCENT']}; width:12px; height:12px; margin:-6px 0; border-radius:10px; }}
QSlider::handle:horizontal:hover {{ border:4px solid {c['ACCENT2']}; }}
QProgressBar {{ background:{c['TRACK']}; border:none; border-radius:6px; max-height:12px; min-height:12px; color:transparent; }}
QProgressBar::chunk {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {c['ACCENT3']}, stop:1 {c['ACCENT2']}); border-radius:6px; }}
QLabel#pillOn {{ background:{rgba(c['ACCENT'], 0.16)}; color:{c['ACCENT']}; border-radius:12px; padding:5px 12px; font-size:9pt; font-weight:700; }}
QLabel#pillOff {{ background:{c['FIELD']}; color:{c['MUTED']}; border-radius:12px; padding:5px 12px; font-size:9pt; font-weight:700; }}
QScrollBar:vertical {{ background:transparent; width:10px; margin:4px 2px; }}
QScrollBar::handle:vertical {{ background:{c['SCROLL']}; border-radius:3px; min-height:40px; margin:0 2px; }}
QScrollBar::handle:vertical:hover {{ background:{c['MUTED']}; margin:0 1px; border-radius:4px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background:transparent; }}
QToolTip {{ background:{c['CARD']}; color:{c['TEXT']}; border:1px solid {c['BORDER']}; padding:5px; border-radius:6px; }}
"""


def make_palette():
    c, pal = C, QPalette()
    for role, v in [(QPalette.Window, c["BG"]), (QPalette.WindowText, c["TEXT"]), (QPalette.Base, c["FIELD"]),
                    (QPalette.AlternateBase, c["CARD"]), (QPalette.Text, c["TEXT"]), (QPalette.Button, c["BTN"]),
                    (QPalette.ButtonText, c["TEXT"]), (QPalette.Highlight, c["ACCENT"]), (QPalette.HighlightedText, c["ON"]),
                    (QPalette.ToolTipBase, c["CARD"]), (QPalette.ToolTipText, c["TEXT"]), (QPalette.PlaceholderText, c["MUTED"])]:
        pal.setColor(role, QColor(v))
    return pal


def apply_app_theme(app):
    cfg = load_cfg()
    set_lang(cfg["ui_lang"])
    t = theme_name(cfg); C.clear(); C.update(THEMES[t], name=t)
    app.setLayoutDirection(Qt.RightToLeft if rtl() else Qt.LeftToRight)
    f = QFont(cfg["ui_font"] or UI_FONT); f.setPointSizeF(10); app.setFont(f)
    app.setStyle("Fusion"); app.setPalette(make_palette()); app.setStyleSheet(build_qss(make_icons()))


class SmoothScroll(QObject):
    """Animated mouse-wheel scrolling (touchpads keep their native pixel scrolling)."""
    def __init__(self, area, step=1.1):
        super().__init__(area)
        self.sb, self.step, self.target = area.verticalScrollBar(), step, None
        self.anim = QPropertyAnimation(self.sb, b"value", self)
        self.anim.setDuration(320); self.anim.setEasingCurve(QEasingCurve.OutCubic)
        area.viewport().installEventFilter(self)

    def eventFilter(self, obj, ev):
        if ev.type() != QEvent.Wheel or ev.modifiers() & Qt.ControlModifier: return False
        if not ev.pixelDelta().isNull() and ev.phase() != Qt.NoScrollPhase: return False
        d = ev.angleDelta().y()
        if not d or self.sb.maximum() <= 0: return False
        base = self.target if (self.anim.state() == QAbstractAnimation.Running and self.target is not None) else self.sb.value()
        self.target = max(self.sb.minimum(), min(self.sb.maximum(), base - d * self.step))
        self.anim.stop(); self.anim.setStartValue(self.sb.value()); self.anim.setEndValue(int(self.target)); self.anim.start()
        return True


def paint_star(p, cx, cy, r, pen):
    """Eight-pointed star (two overlapping squares) used as a decorative motif."""
    p.save(); p.setPen(pen); p.setBrush(Qt.NoBrush)
    for a in (0, 45):
        p.save(); p.translate(cx, cy); p.rotate(a); p.drawRoundedRect(QRectF(-r, -r, 2 * r, 2 * r), r * 0.08, r * 0.08); p.restore()
    p.drawEllipse(QPointF(cx, cy), r * 0.42, r * 0.42)
    p.restore()


class Sidebar(QFrame):
    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        col = QColor(C["ACCENT"]); col.setAlpha(26)
        W, H = self.width(), self.height()
        for i, (x, y, r) in enumerate([(W * 0.15, H * 0.74, 58), (W * 0.78, H * 0.86, 40), (W * 0.36, H * 0.97, 30)]):
            paint_star(p, x, y, r, QPen(col, 1.4))
        p.setPen(QPen(QColor(C["BORDER"]), 1))
        x = 0.5 if rtl() else W - 0.5
        p.drawLine(QPointF(x, 0), QPointF(x, H))
        p.end()


# ---------------------------------------------------------------- settings window: widgets
def lbl(text, name=None, wrap=False):
    l = QLabel(text)
    if name: l.setObjectName(name)
    l.setWordWrap(wrap)
    return l


def card(title=None, subtitle=None):
    fr = QFrame(); fr.setObjectName("card")
    v = QVBoxLayout(fr); v.setContentsMargins(20, 18, 20, 20); v.setSpacing(12)
    if title: v.addWidget(lbl(title, "h2"))
    if subtitle: v.addWidget(lbl(subtitle, "muted", True))
    return fr, v


def field(label, widget, value_label=None):
    w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(6)
    if value_label is not None:
        h = QHBoxLayout(); h.addWidget(lbl(label.upper(), "field")); h.addStretch(); h.addWidget(value_label)
        v.addLayout(h)
    else:
        v.addWidget(lbl(label.upper(), "field"))
    v.addWidget(widget)
    return w


def switch(text, desc=None):
    w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(2)
    cb = QCheckBox(text); cb.setCursor(Qt.PointingHandCursor); v.addWidget(cb)
    if desc:
        d = lbl(desc, "small", True)
        d.setContentsMargins(*((0, 0, 50, 0) if rtl() else (50, 0, 0, 0))); v.addWidget(d)
    return w, cb


def slider(lo, hi, val, fmt, step=1):
    s = QSlider(Qt.Horizontal); s.setRange(lo, hi); s.setSingleStep(step); s.setPageStep(step * 5)
    l = lbl("", "value"); s.valueChanged.connect(lambda x: l.setText(fmt(x))); s.setValue(int(val)); l.setText(fmt(s.value()))
    return s, l


def segmented(labels, checked=0, icons=None, tips=None):
    w = QWidget(); h = QHBoxLayout(w); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(0)
    g = QButtonGroup(w)
    first, last = ("last", "first") if rtl() else ("first", "last")  # physical corners flip in RTL
    for i, t in enumerate(labels):
        b = QPushButton(t); b.setObjectName("iconseg" if icons else "seg"); b.setCheckable(True); b.setCursor(Qt.PointingHandCursor)
        if icons: b.setIcon(icon(icons[i], C["SUB"])); b.setIconSize(QSize(18, 18))
        if tips: b.setToolTip(tips[i])
        if i == 0: b.setProperty(first, True)
        if i == len(labels) - 1: b.setProperty(last, True)
        g.addButton(b, i); h.addWidget(b, 1)
    g.button(checked).setChecked(True)
    return w, g


class ColorButton(QPushButton):
    def __init__(self, color, on_change):
        super().__init__(); self.on_change = on_change; self.setCursor(Qt.PointingHandCursor)
        self.clicked.connect(self.pick); self.set(color)

    def set(self, color):
        self.color = color
        pm = QPixmap(36, 36); pm.fill(Qt.transparent)
        p = QPainter(pm); p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(C["MUTED"]), 2)); p.setBrush(QColor(color)); p.drawEllipse(2, 2, 32, 32); p.end()
        self.setIcon(QIcon(pm)); self.setIconSize(QSize(18, 18)); self.setText("  " + color.upper())

    def pick(self):
        c = QColorDialog.getColor(QColor(self.color), self, T("pick_color"))
        if c.isValid(): self.set(c.name()); self.on_change()


class RecDelegate(QStyledItemDelegate):
    def sizeHint(self, opt, idx):
        return QSize(200, 60)

    def paint(self, p, opt, idx):
        r = idx.data(Qt.UserRole); n = idx.data(Qt.UserRole + 1) or 0
        if not r: return
        R = rtl()
        p.save(); p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(opt.rect).adjusted(6 if R else 2, 2, -2 if R else -6, -2)
        sel, hov = bool(opt.state & QStyle.State_Selected), bool(opt.state & QStyle.State_MouseOver)
        if sel or hov:
            ac = QColor(C["ACCENT"]); fill = QColor(ac); fill.setAlpha(34); hv = QColor(C["TEXT"]); hv.setAlpha(12)
            p.setPen(QPen(ac, 1.2) if sel else Qt.NoPen); p.setBrush(fill if sel else hv)
            p.drawRoundedRect(rect, 12, 12)
        x = rect.adjusted(14, 9, -14, -9)
        main = QRectF(x)
        f2 = QFont(opt.font); f2.setPointSizeF(opt.font.pointSizeF() - 1)
        if n:
            badge = f"⤓ {n}"; bw = QFontMetricsF(f2).horizontalAdvance(badge) + 18
            bx = x.left() if R else x.right() - bw
            b = QRectF(bx, x.center().y() - 11, bw, 22)
            bc = QColor(C["ACCENT"]); bc.setAlpha(40)
            p.setPen(Qt.NoPen); p.setBrush(bc); p.drawRoundedRect(b, 11, 11)
            p.setFont(f2); p.setPen(QColor(C["ACCENT"])); p.drawText(b, Qt.AlignCenter, badge)
            if R: main.setLeft(b.right() + 10)
            else: main.setRight(b.left() - 10)
        title = r["ar"] if R else (r["en"] or r["ar"])
        other = (r["en"] or "") if R else r["ar"]
        style = r["style"].replace("Rewayat ", "").replace("Almusshaf Al ", "").replace(" A'n ", " ʿan ")
        if r["count"] < 114: style += "  ·  " + T("n_surahs", n=r["count"])
        A = (Qt.AlignRight if R else Qt.AlignLeft) | Qt.AlignAbsolute
        B = (Qt.AlignLeft if R else Qt.AlignRight) | Qt.AlignAbsolute
        fo = QFont(opt.font); fo.setPointSizeF(opt.font.pointSizeF() + (0 if R else 1.5))
        ow = min(QFontMetricsF(fo).horizontalAdvance(other), main.width() * 0.42) if other else 0
        p.setFont(fo); p.setPen(QColor(C["SUB"]))
        if other: p.drawText(main, B | Qt.AlignVCenter, QFontMetricsF(fo).elidedText(other, Qt.ElideRight, ow + 1))
        tx = QRectF(main)
        if R: tx.setLeft(main.left() + ow + 14)
        else: tx.setRight(main.right() - ow - 14)
        f = QFont(opt.font); f.setPointSizeF(opt.font.pointSizeF() + (1.5 if R else 0.5)); f.setWeight(QFont.DemiBold)
        p.setFont(f); p.setPen(QColor(C["ACCENT"] if sel else C["TEXT"]))
        p.drawText(tx, A | Qt.AlignTop, QFontMetricsF(f).elidedText(title, Qt.ElideRight, tx.width()))
        p.setFont(f2); p.setPen(QColor(C["MUTED"]))
        p.drawText(tx, A | Qt.AlignBottom, QFontMetricsF(f2).elidedText(style, Qt.ElideRight, tx.width()))
        p.restore()


class Preview(QWidget):
    SAMPLE = ("ٱلْحَمْدُ لِلَّهِ رَبِّ ٱلْعَٰلَمِينَ", "All praise is due to Allah, Lord of the worlds.", 2)

    def __init__(self, get_cfg, qfont):
        super().__init__(); self.get_cfg, self.qfont = get_cfg, qfont; self.setMinimumHeight(270)
        self.long = None  # (ar, tr, n) of a long verse, filled when loaded
        self.setLayoutDirection(Qt.LeftToRight)

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        W, H = self.width(), self.height()
        clip = QPainterPath(); clip.addRoundedRect(QRectF(0, 0, W, H), 12, 12); p.setClipPath(clip)
        g = QLinearGradient(0, 0, W, H); g.setColorAt(0, QColor("#1d3557")); g.setColorAt(1, QColor("#5b2a62"))
        p.fillRect(self.rect(), g)
        for x, y, w, h, c in [(0.05, 0.08, 0.5, 0.7, "#f3f4f6"), (0.44, 0.2, 0.5, 0.72, "#22272f")]:
            r = QRectF(W * x, H * y, W * w, H * h)
            p.setPen(Qt.NoPen); p.setBrush(QColor(c)); p.drawRoundedRect(r, 8, 8)
            p.setBrush(QColor(0, 0, 0, 28)); p.drawRoundedRect(QRectF(r.x(), r.y(), r.width(), 22), 8, 8)
            p.setBrush(QColor(128, 128, 128, 80))
            for k in range(6):
                p.drawRoundedRect(QRectF(r.x() + 16, r.y() + 38 + k * 17, r.width() * (0.35 + 0.15 * (k % 3)), 7), 3, 3)
        c0 = self.get_cfg()
        k = min(1.0, max(0.2, W / max(1, QApplication.primaryScreen().geometry().width())))
        ar, tr, n = self.long or self.SAMPLE
        for _ in range(8):  # scale like the real screen; shrink more if the page would not fit the preview
            c = dict(c0, size=max(6, c0["size"] * k), margin=int(c0["margin"] * k))
            pages = paginate(ar + "\u00a0﴿" + ar_digits(n) + "﴾", tr if c.get("has_tr") else "", c, self.qfont,
                             W * c["max_width"] / 100)
            lines, h = page_lines(pages[0], c, self.qfont)
            h += 30
            if h + c["margin"] <= H - 6: break
            k *= 0.85
        p.save(); p.translate(0, c["margin"] if c["pos"] == "top" else H - h - c["margin"])
        paint_lines(p, W, h, lines, c); p.restore()
        if len(pages) > 1:
            f = QFont(self.font()); f.setPointSizeF(8.5); f.setWeight(QFont.DemiBold); p.setFont(f)
            t = T("preview_page", k=1, n=len(pages)); tw = QFontMetricsF(f).horizontalAdvance(t) + 20
            r = QRectF(W - tw - 10, 10, tw, 22); p.setPen(Qt.NoPen); p.setBrush(QColor(0, 0, 0, 120)); p.drawRoundedRect(r, 11, 11)
            p.setPen(QColor("#ffffff")); p.drawText(r, Qt.AlignCenter, t)
        p.end()


class FitStack(QStackedWidget):
    """A stack that only takes the size of the page being shown."""
    def sizeHint(self):
        w = self.currentWidget(); return w.sizeHint() if w else super().sizeHint()

    def minimumSizeHint(self):
        w = self.currentWidget(); return w.minimumSizeHint() if w else super().minimumSizeHint()


# ---------------------------------------------------------------- settings window
WINDOWS = []


class UI(QWidget):
    MODES = ["recite", "memorize", "manual"]
    ADV = ["words", "fixed", "reciter"]
    HINTS = ["none", "reveal", "fade"]

    def __init__(self, page=0):
        super().__init__()
        self.setObjectName("root"); self.setWindowTitle(T("app_title"))
        self.setWindowIcon(QIcon(os.path.join(HERE, "icons", "logo.png")))
        self.resize(1140, 840); self.setMinimumSize(960, 660)
        self.cfg = load_cfg(); self.bus = Bus(); self.recs, self.sur, self.trs = [], [], []
        self.cancel, self.dl_busy = False, False
        self.qfont = register_fonts()
        self.style_timer = QTimer(self); self.style_timer.setSingleShot(True)
        self.style_timer.timeout.connect(self.apply_style)

        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)
        body = QHBoxLayout(); body.setSpacing(0); outer.addLayout(body, 1)
        self.stack = QStackedWidget()
        body.addWidget(self.build_sidebar()); body.addWidget(self.stack, 1)
        for build in (self.build_recite, self.build_appearance, self.build_downloads):
            self.stack.addWidget(self.scroll(build()))
        outer.addWidget(self.build_bar())
        self.nav.button(page).setChecked(True); self.stack.setCurrentIndex(page)

        self.bus.data.connect(self.populate)
        self.bus.dl.connect(self.on_dl)
        threading.Thread(target=self.load_data, daemon=True).start()
        nt = QTimer(self); nt.timeout.connect(self.refresh_now); nt.start(1500); self.refresh_now()

    # ---------- layout ----------
    def paintEvent(self, _):  # soft background with glowing shapes
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        W, H = self.width(), self.height()
        p.fillRect(self.rect(), QColor(C["BG"]))
        from PySide6.QtGui import QRadialGradient
        for cx, cy, r, a in [(0.88, 0.05, 520, C["BLOB"]), (0.42, 1.0, 460, C["BLOB"] * 0.7)]:
            x = (1 - cx) * W if rtl() else cx * W
            g = QRadialGradient(QPointF(x, cy * H), r)
            c1 = QColor(C["ACCENT"]); c1.setAlpha(int(a)); c2 = QColor(C["ACCENT"]); c2.setAlpha(0)
            g.setColorAt(0, c1); g.setColorAt(1, c2); p.fillRect(self.rect(), g)
        col = QColor(C["ACCENT"]); col.setAlpha(20)
        paint_star(p, (W - 150) if not rtl() else 150, 120, 70, QPen(col, 1.5))
        p.end()

    def scroll(self, w):
        w.setObjectName("page")
        sa = QScrollArea(); sa.setWidgetResizable(True); sa.setWidget(w); sa.setFrameShape(QFrame.NoFrame)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sa.viewport().setAutoFillBackground(False); w.setAutoFillBackground(False)
        SmoothScroll(sa)
        return sa

    def header(self, v, title, sub, ic=None):
        row = QHBoxLayout(); row.setSpacing(14)
        if ic:
            t = QLabel(); t.setPixmap(tile_icon(ic, True).pixmap(QSize(44, 44))); row.addWidget(t, 0, Qt.AlignTop)
        col = QVBoxLayout(); col.setSpacing(2); col.addWidget(lbl(title, "h1")); col.addWidget(lbl(sub, "muted", True))
        row.addLayout(col, 1); v.addLayout(row); v.addSpacing(4)

    def build_sidebar(self):
        side = Sidebar(); side.setObjectName("side"); side.setFixedWidth(248)
        v = QVBoxLayout(side); v.setContentsMargins(18, 22, 18, 18); v.setSpacing(4)
        top = QHBoxLayout(); top.setSpacing(12)
        logo = QLabel(); logo.setPixmap(tile_icon("star8", True).pixmap(QSize(50, 50))); top.addWidget(logo, 0, Qt.AlignVCenter)
        tv = QVBoxLayout(); tv.setSpacing(0)
        tv.addWidget(lbl("القرآن الكريم", "brandAr")); tv.addWidget(lbl(T("app_title"), "brand"))
        top.addLayout(tv, 1); v.addLayout(top)
        v.addSpacing(4); v.addWidget(lbl(T("app_sub"), "small", True)); v.addSpacing(18)
        self.nav = QButtonGroup(self)
        for i, (t, ic) in enumerate([(T("nav_recite"), "book"), (T("nav_appearance"), "palette"), (T("nav_downloads"), "cloud")]):
            b = QPushButton("  " + t); b.setObjectName("nav"); b.setCheckable(True); b.setCursor(Qt.PointingHandCursor)
            b.setIcon(tile_icon(ic)); b.setIconSize(QSize(34, 34))
            if rtl(): b.setStyleSheet("text-align:right;")
            self.nav.addButton(b, i); v.addWidget(b)
        self.nav.idClicked.connect(self.go)
        v.addStretch()
        themes = ["system", "light", "dark"]
        seg, self.themeg = segmented(["", "", ""], themes.index(self.cfg.get("theme", "system")) if self.cfg.get("theme") in themes else 0,
                                     icons=["auto", "sun", "moon"], tips=[T("theme_system"), T("theme_light"), T("theme_dark")])
        self.themeg.idClicked.connect(lambda i: self.change_theme(themes[i]))
        v.addWidget(field(T("theme"), seg)); v.addSpacing(8)
        self.langbox = QComboBox()
        cur = LANG["code"]
        for code, name, _ in lang_list():
            self.langbox.addItem(icon("globe", C["SUB"]), name, code)
            if code == cur: self.langbox.setCurrentIndex(self.langbox.count() - 1)
        self.langbox.currentIndexChanged.connect(self.change_lang)
        v.addWidget(field(T("language"), self.langbox)); v.addSpacing(10)
        sc = QFrame(); sc.setObjectName("shortcuts"); sv = QVBoxLayout(sc); sv.setContentsMargins(14, 12, 14, 12); sv.setSpacing(6)
        hr = QHBoxLayout(); kb = QLabel(); kb.setPixmap(icon("keyboard", C["MUTED"]).pixmap(QSize(16, 16)))
        hr.addWidget(kb); hr.addWidget(lbl(T("shortcuts").upper(), "field")); hr.addStretch(); sv.addLayout(hr)
        sv.addWidget(lbl(T("shortcuts_hold"), "small", True))
        for k, d in [("Q", "sc_toggle"), ("Space", "sc_pause"), ("← →", "sc_ayah"), ("PgUp/Dn", "sc_surah"),
                     ("↑ ↓", "sc_size"), ("H", "sc_hide"), ("S", "sc_window")]:
            r = QHBoxLayout(); r.addWidget(lbl(k, "kbd")); r.addStretch(); r.addWidget(lbl(T(d), "small"))
            sv.addLayout(r)
        v.addWidget(sc)
        return side

    def go(self, i):
        self.stack.setCurrentIndex(i)
        if i == 2: self.update_dl_info(); self.fill_lib()

    def build_recite(self):
        c = self.cfg
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(32, 22, 32, 22); v.setSpacing(14)
        self.header(v, T("recite_title"), T("recite_sub"), "book")
        h = QHBoxLayout(); h.setSpacing(18); v.addLayout(h, 1)
        left = QVBoxLayout(); left.setSpacing(18); h.addLayout(left, 5)

        cs, cv = card(T("surah"))
        self.surah = QComboBox(); self.surah.setEditable(True); self.surah.setInsertPolicy(QComboBox.NoInsert)
        self.surah.lineEdit().setPlaceholderText(T("search_surah"))
        self.surah.completer().setFilterMode(Qt.MatchContains)
        self.surah.completer().setCompletionMode(QCompleter.PopupCompletion)
        self.surah.currentIndexChanged.connect(self.surah_changed)
        cv.addWidget(field(T("surah"), self.surah))
        self.ayah = QSpinBox(); self.ayah.setRange(1, 286)
        self.ayah_to = QSpinBox(); self.ayah_to.setRange(0, 286); self.ayah_to.setSpecialValueText(T("to_end"))
        sw, self.loop = switch(T("loop")); self.loop.setChecked(c["loop"])
        row = QHBoxLayout(); row.addWidget(field(T("from_ayah"), self.ayah)); row.addWidget(field(T("to_ayah"), self.ayah_to))
        row.addWidget(sw, 0, Qt.AlignBottom); cv.addLayout(row)
        self.surah_ar = lbl("", "quran"); self.surah_ar.setFont(QFont(self.qfont, 22))
        self.surah_ar.setAlignment(Qt.AlignCenter); self.surah_ar.setMinimumHeight(50); cv.addWidget(self.surah_ar)
        self.surah_meta = lbl("", "small"); self.surah_meta.setAlignment(Qt.AlignCenter); cv.addWidget(self.surah_meta)
        left.addWidget(cs)

        cm, cv = card(T("mode"))
        segw, self.modeg = segmented([T("mode_recite"), T("mode_memorize"), T("mode_manual")],
                                     self.MODES.index(c["mode"]))
        cv.addWidget(segw)
        self.modedesc = lbl("", "modedesc", True); cv.addWidget(self.modedesc)
        self.trans = QComboBox(); self.trans.currentIndexChanged.connect(lambda *_: self.preview.update())
        cv.addWidget(field(T("translation"), self.trans))
        self.modeopts = FitStack(); self.modeopts.setObjectName("modeopts")
        # recite options
        o = QWidget(); ov = QVBoxLayout(o); ov.setContentsMargins(0, 0, 0, 0); ov.setSpacing(12)
        self.speed, sl = slider(50, 200, round(float(c["speed"]) * 100), lambda x: f"{x / 100:.2f}×", 5)
        self.volume, vl = slider(0, 100, c["volume"], lambda x: f"{x}%")
        row = QHBoxLayout(); row.setSpacing(18); row.addWidget(field(T("speed"), self.speed, sl)); row.addWidget(field(T("volume"), self.volume, vl))
        ov.addLayout(row)
        sw, self.autonext = switch(T("autonext")); self.autonext.setChecked(c["autonext"]); ov.addWidget(sw)
        sw, self.wordsync = switch(T("word_sync"), T("word_sync_desc")); self.wordsync.setChecked(c["word_sync"]); ov.addWidget(sw)
        self.modeopts.addWidget(o)
        # memorize options
        o = QWidget(); ov = QVBoxLayout(o); ov.setContentsMargins(0, 0, 0, 0); ov.setSpacing(12)
        self.adv = QComboBox()
        for k in self.ADV: self.adv.addItem(T("adv_" + k), k)
        self.adv.setCurrentIndex(self.ADV.index(c["mem_advance"]) if c["mem_advance"] in self.ADV else 0)
        ov.addWidget(field(T("advance"), self.adv))
        self.advopts = FitStack(); self.advopts.setObjectName("modeopts")
        a = QWidget(); ah = QHBoxLayout(a); ah.setContentsMargins(0, 0, 0, 0); ah.setSpacing(18)
        self.perword, l1 = slider(3, 30, round(float(c["mem_per_word"]) * 10), lambda x: T("sec_per_word", s=f"{x / 10:.1f}"))
        self.memmin, l2 = slider(1, 30, round(float(c["mem_min"])), lambda x: T("secs", s=x))
        ah.addWidget(field(T("per_word"), self.perword, l1)); ah.addWidget(field(T("minimum"), self.memmin, l2))
        self.advopts.addWidget(a)
        a = QWidget(); ah = QHBoxLayout(a); ah.setContentsMargins(0, 0, 0, 0)
        self.memfixed, l3 = slider(2, 120, round(float(c["mem_fixed"])), lambda x: T("secs", s=x))
        ah.addWidget(field(T("per_verse"), self.memfixed, l3)); self.advopts.addWidget(a)
        a = QWidget(); ah = QHBoxLayout(a); ah.setContentsMargins(0, 0, 0, 0)
        ah.addWidget(lbl(T("adv_reciter_desc"), "small", True)); self.advopts.addWidget(a)
        ov.addWidget(self.advopts)
        self.adv.currentIndexChanged.connect(lambda i: self.fit_stack(self.advopts, i))
        self.memgap, l4 = slider(0, 20, round(float(c["mem_gap"])), lambda x: T("secs", s=x) if x else T("off"))
        self.memrep = QSpinBox(); self.memrep.setRange(1, 20); self.memrep.setValue(int(c["mem_repeat"])); self.memrep.setSuffix(" ×")
        row = QHBoxLayout(); row.setSpacing(18); row.addWidget(field(T("gap"), self.memgap, l4), 1); row.addWidget(field(T("repeat"), self.memrep))
        ov.addLayout(row)
        self.hint = QComboBox()
        for k in self.HINTS: self.hint.addItem(T("hint_" + k), k)
        self.hint.setCurrentIndex(self.HINTS.index(c["mem_hint"]) if c["mem_hint"] in self.HINTS else 0)
        self.hintwords = QSpinBox(); self.hintwords.setRange(1, 10); self.hintwords.setValue(int(c["hint_words"]))
        self.hintdelay, l5 = slider(1, 30, round(float(c["hint_delay"])), lambda x: T("secs", s=x))
        row = QHBoxLayout(); row.setSpacing(18); row.addWidget(field(T("helper"), self.hint), 2)
        self.hw_field = field(T("hint_words"), self.hintwords); row.addWidget(self.hw_field)
        self.hd_field = field(T("hint_delay"), self.hintdelay, l5); row.addWidget(self.hd_field, 2)
        ov.addLayout(row)
        self.hint.currentIndexChanged.connect(self.hint_changed)
        self.modeopts.addWidget(o)
        # manual
        o = QWidget(); ov = QVBoxLayout(o); ov.setContentsMargins(0, 0, 0, 0)
        ov.addWidget(lbl(T("manual_desc"), "small", True)); self.modeopts.addWidget(o)
        cv.addWidget(self.modeopts)
        self.modeg.idClicked.connect(self.mode_changed)
        left.addWidget(cm)
        left.addStretch()
        self.playbtn = QPushButton(T("start")); self.playbtn.setObjectName("primary")
        self.playbtn.setCursor(Qt.PointingHandCursor); self.playbtn.clicked.connect(self.play)
        self.playbtn.setIcon(icon("play", C["ON"], mirror=False)); self.playbtn.setIconSize(QSize(18, 18))
        left.addWidget(self.playbtn)

        cr, cv = card()
        row = QHBoxLayout(); row.addWidget(lbl(T("reciter"), "h2")); row.addStretch()
        self.reccount = lbl(T("loading"), "small"); row.addWidget(self.reccount); cv.addLayout(row)
        self.search = QLineEdit(); self.search.setPlaceholderText(T("search_reciter"))
        self.search.setClearButtonEnabled(True); self.search.textChanged.connect(self.filter_recs); cv.addWidget(self.search)
        self.reclist = QListWidget(); self.reclist.setItemDelegate(RecDelegate(self.reclist))
        self.reclist.setMouseTracking(True); self.reclist.setMinimumHeight(340)
        self.reclist.setVerticalScrollMode(QListWidget.ScrollPerPixel); self.reclist.verticalScrollBar().setSingleStep(24)
        SmoothScroll(self.reclist, 1.0)
        self.search.addAction(icon("search", C["MUTED"]), QLineEdit.LeadingPosition)
        self.reclist.currentItemChanged.connect(lambda *_: self.update_dl_info())
        self.reclist.itemDoubleClicked.connect(lambda *_: self.play())
        cv.addWidget(self.reclist, 1)
        self.rechint = lbl("", "small", True); cv.addWidget(self.rechint)
        cr.setMinimumWidth(380)
        h.addWidget(cr, 6)
        for cb in w.findChildren(QComboBox):  # long items must not widen the column
            cb.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon); cb.setMinimumContentsLength(12)
        self.mode_changed(self.modeg.checkedId()); self.fit_stack(self.advopts, self.adv.currentIndex()); self.hint_changed()
        return w

    @staticmethod
    def fit_stack(st, i):
        st.setCurrentIndex(i)
        for j in range(st.count()):
            st.widget(j).setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred if j == i else QSizePolicy.Ignored)
        st.updateGeometry()

    def mode_changed(self, i):
        self.fit_stack(self.modeopts, i)
        m = self.MODES[i]
        self.modedesc.setText(T("mode_desc_" + m))
        self.rechint.setText(T("rec_hint_" + m))

    def hint_changed(self, *_):
        h = self.hint.currentData()
        self.hw_field.setVisible(h == "reveal"); self.hd_field.setVisible(h == "reveal")

    def build_appearance(self):
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(32, 22, 32, 22); v.setSpacing(14)
        self.header(v, T("appearance_title"), T("appearance_sub"), "palette")
        c = self.cfg; ch = self.style_changed
        pc, pv = card()
        row = QHBoxLayout(); row.addWidget(lbl(T("preview"), "h2")); row.addStretch(); row.addWidget(lbl(T("preview_note"), "small"))
        pv.addLayout(row)
        self.preview = Preview(lambda: dict(self.style_values(), has_tr=bool(self.trans.currentData())), self.qfont)
        pv.addWidget(self.preview); v.addWidget(pc)

        g = QGridLayout(); g.setSpacing(18); v.addLayout(g)
        c1, cv = card(T("arabic_text"))
        self.font = QFontComboBox(); self.font.setWritingSystem(QFontDatabase.WritingSystem.Arabic)
        self.font.setCurrentFont(QFont(c["font"] or self.qfont))
        self.size, l = slider(16, 120, c["size"], lambda x: f"{x} pt")
        cv.addWidget(field(T("font"), self.font)); cv.addWidget(field(T("size"), self.size, l))
        g.addWidget(c1, 0, 0)

        c2, cv = card(T("translation_text"))
        self.trfont = QFontComboBox(); self.trfont.setCurrentFont(QFont(c["tr_font"]))
        self.trscale, l = slider(20, 120, c["tr_scale"], lambda x: T("pct_of_arabic", p=x))
        cv.addWidget(field(T("font"), self.trfont)); cv.addWidget(field(T("size"), self.trscale, l))
        g.addWidget(c2, 0, 1)

        c3, cv = card(T("layout"), T("layout_desc"))
        self.maxlines, l1 = slider(1, 6, c["max_lines"], lambda x: T("n_lines", n=x))
        self.maxwidth, l2 = slider(30, 100, c["max_width"], lambda x: T("pct_of_screen", p=x))
        self.trlines, l3 = slider(1, 4, c["tr_lines"], lambda x: T("n_lines", n=x))
        cv.addWidget(field(T("max_lines"), self.maxlines, l1)); cv.addWidget(field(T("max_width"), self.maxwidth, l2))
        cv.addWidget(field(T("tr_lines"), self.trlines, l3))
        g.addWidget(c3, 1, 0)

        c4, cv = card(T("colour_outline"))
        self.color = ColorButton(c["color"], ch); self.outline = ColorButton(c["outline"], ch)
        row = QHBoxLayout(); row.addWidget(field(T("text_colour"), self.color)); row.addWidget(field(T("outline"), self.outline)); cv.addLayout(row)
        self.outw, l = slider(0, 15, c["outline_w"], lambda x: T("off") if x == 0 else str(x))
        cv.addWidget(field(T("outline_w"), self.outw, l))
        g.addWidget(c4, 1, 1)

        c5, cv = card(T("bg_position"))
        sw, self.bg = switch(T("bg_box")); self.bg.setChecked(c["bg"]); cv.addWidget(sw)
        self.bgcolor = ColorButton(c["bg_color"], ch)
        self.bgalpha, l = slider(0, 100, c["bg_alpha"], lambda x: f"{x}%")
        row = QHBoxLayout(); row.addWidget(field(T("box_colour"), self.bgcolor)); row.addWidget(field(T("opacity"), self.bgalpha, l), 1)
        cv.addLayout(row)
        seg, self.posgroup = segmented([T("bottom"), T("top")], 1 if c["pos"] == "top" else 0)
        self.margin, l = slider(0, 600, c["margin"], lambda x: f"{x} px")
        row = QHBoxLayout(); row.addWidget(field(T("position"), seg)); row.addWidget(field(T("distance"), self.margin, l), 1)
        cv.addLayout(row)
        g.addWidget(c5, 2, 0)

        c6, cv = card(T("interface"), T("interface_desc"))
        self.uifont = QFontComboBox(); self.uifont.setCurrentFont(QFont(c["ui_font"] or UI_FONT))
        cv.addWidget(field(T("ui_font"), self.uifont))
        b = QPushButton(T("apply")); b.clicked.connect(self.change_ui_font); cv.addWidget(b, 0, Qt.AlignLeft if not rtl() else Qt.AlignRight)
        cv.addStretch()
        g.addWidget(c6, 2, 1)
        g.setColumnStretch(0, 1); g.setColumnStretch(1, 1)

        row = QHBoxLayout(); row.addStretch()
        b = QPushButton(T("reset")); b.setIcon(icon("reset", C["SUB"])); b.clicked.connect(self.reset_style); row.addWidget(b); v.addLayout(row)
        v.addStretch()
        for x in (self.font, self.trfont): x.currentFontChanged.connect(ch)
        for x in (self.size, self.trscale, self.outw, self.margin, self.bgalpha, self.maxlines, self.maxwidth, self.trlines):
            x.valueChanged.connect(ch)
        self.bg.toggled.connect(ch); self.posgroup.idClicked.connect(ch)
        return w

    def build_downloads(self):
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(32, 22, 32, 22); v.setSpacing(14)
        self.header(v, T("downloads_title"), T("downloads_sub"), "cloud")
        c, cv = card()
        cv.addWidget(lbl(T("selected_reciter").upper(), "field"))
        self.dlname = lbl("—", "bigname"); cv.addWidget(self.dlname)
        self.dlsub = lbl("", "muted"); cv.addWidget(self.dlsub)
        row = QHBoxLayout(); row.setSpacing(28)
        self.st_n, self.st_mb = lbl("0", "stat"), lbl("0", "stat")
        for big, small in [(self.st_n, T("surahs_downloaded")), (self.st_mb, T("mb_on_disk"))]:
            col = QVBoxLayout(); col.setSpacing(0); col.addWidget(big); col.addWidget(lbl(small, "small")); row.addLayout(col)
        row.addStretch(); cv.addLayout(row)
        self.prog = QProgressBar(); self.prog.setTextVisible(False); cv.addWidget(self.prog)
        self.dlstatus = lbl(T("dl_hint"), "small"); cv.addWidget(self.dlstatus)
        row = QHBoxLayout()
        self.b_all = QPushButton(T("dl_all")); self.b_all.setObjectName("primary"); self.b_all.setCursor(Qt.PointingHandCursor)
        self.b_all.setIcon(icon("download", C["ON"])); self.b_all.setIconSize(QSize(18, 18))
        self.b_all.clicked.connect(lambda: self.download(list(range(1, 115))))
        self.b_one = QPushButton(T("dl_one", name="")); self.b_one.clicked.connect(lambda: self.download([self.surah.currentIndex() + 1]))
        self.b_cancel = QPushButton(T("cancel")); self.b_cancel.setEnabled(False)
        self.b_cancel.clicked.connect(lambda: setattr(self, "cancel", True))
        row.addWidget(self.b_all); row.addWidget(self.b_one); row.addStretch(); row.addWidget(self.b_cancel)
        cv.addLayout(row)
        v.addWidget(c)

        c, cv = card(T("library"), T("library_desc"))
        self.lib = QListWidget(); self.lib.setObjectName("lib"); self.lib.setMinimumHeight(160)
        self.lib.setVerticalScrollMode(QListWidget.ScrollPerPixel); SmoothScroll(self.lib, 0.8)
        self.lib.itemClicked.connect(self.lib_select); cv.addWidget(self.lib)
        row = QHBoxLayout()
        b = QPushButton(T("open_folder")); b.setIcon(icon("folder", C["SUB"])); b.clicked.connect(self.open_folder); row.addWidget(b)
        row.addStretch()
        b = QPushButton(T("delete_dl")); b.setObjectName("danger"); b.setIcon(icon("trash", "#ef4444")); b.clicked.connect(self.delete_dl)
        row.addWidget(b); cv.addLayout(row)
        cv.addWidget(lbl(LIB, "small"))
        v.addWidget(c); v.addStretch()
        return w

    def build_bar(self):
        bar = QFrame(); bar.setObjectName("bar"); bar.setFixedHeight(84)
        h = QHBoxLayout(bar); h.setContentsMargins(24, 8, 24, 8)
        info = QWidget(); iv = QVBoxLayout(info); iv.setContentsMargins(0, 0, 0, 0); iv.setSpacing(2)
        self.np_name = lbl("", "npname"); self.np_sub = lbl("", "small")
        iv.addWidget(self.np_name); iv.addWidget(self.np_sub)
        h.addWidget(info, 1)
        mid = QHBoxLayout(); mid.setSpacing(12)
        for ic, tip, fn, name in [("prev", T("prev_ayah"), lambda: send("prev"), "round"),
                                  ("play", T("play_pause"), self.play_pause, "roundMain"),
                                  ("next", T("next_ayah"), lambda: send("next"), "round"),
                                  ("stop", T("stop"), self.stop, "round")]:
            b = QPushButton(); b.setObjectName(name); b.setToolTip(tip); b.setCursor(Qt.PointingHandCursor)
            main_ = name == "roundMain"
            b.setIcon(icon(ic, C["ON"] if main_ else C["SUB"], mirror=None if ic != "play" else False))
            b.setIconSize(QSize(24, 24) if main_ else QSize(18, 18))
            b.clicked.connect(fn); mid.addWidget(b)
            if main_:
                self.ppbtn = b
                glow = QGraphicsDropShadowEffect(b); glow.setBlurRadius(26); glow.setOffset(0, 4)
                gc = QColor(C["ACCENT"]); gc.setAlpha(C["GLOW"]); glow.setColor(gc); b.setGraphicsEffect(glow)
        h.addLayout(mid)
        right = QHBoxLayout(); right.setSpacing(14); right.addStretch()
        self.showsw = QCheckBox(T("show_on_screen")); self.showsw.setCursor(Qt.PointingHandCursor)
        self.showsw.setToolTip(T("show_on_screen_tip")); self.showsw.toggled.connect(self.toggle_visible)
        right.addWidget(self.showsw, 0, Qt.AlignVCenter)
        self.pill = QLabel(); right.addWidget(self.pill, 0, Qt.AlignVCenter)
        rw = QWidget(); rw.setLayout(right); h.addWidget(rw, 1)
        return bar

    # ---------- data ----------
    def load_data(self):
        try:
            res = (reciters(), surahs(), translations())
        except Exception as e:
            self.bus.data.emit(str(e)); return
        self.bus.data.emit(res)
        try:  # a long verse for the preview (Ayat al-Kursi)
            _, it = surah_text(2, self.cfg["trans"] or "en.sahih")
            self.bus.data.emit(("long", it[255]["ar"], it[255]["tr"], 255))
        except Exception:
            pass

    def surah_label(self, s):
        return T("surah_item", n=s["number"], en=s["englishName"], meaning=s["englishNameTranslation"],
                 ar=s["name"].replace("سُورَةُ ", ""), ayahs=s["numberOfAyahs"])

    def populate(self, res):
        if isinstance(res, str):
            self.reccount.setText(T("offline")); self.dlstatus.setText(res); return
        if res[0] == "long":
            self.preview.long = res[1:]; self.preview.update(); return
        self.recs, self.sur, self.trs = res
        self.surah.blockSignals(True)
        for s in self.sur: self.surah.addItem(self.surah_label(s), s["numberOfAyahs"])
        self.surah.setCurrentIndex(self.cfg["surah"] - 1); self.surah.blockSignals(False)
        n = self.surah.currentData() or 286
        self.ayah.setMaximum(n); self.ayah_to.setMaximum(n)
        self.ayah.setValue(self.cfg["range_from"] if self.cfg["range_to"] else self.cfg["ayah"])
        self.ayah_to.setValue(min(self.cfg["range_to"], n))
        self.show_surah_info()
        self.trans.blockSignals(True)
        self.trans.addItem(T("no_translation"), "")
        for e in sorted(self.trs, key=lambda e: (e["language"], e["englishName"])):
            self.trans.addItem(f"{e['language'].upper()}  ·  {e['englishName']}", e["identifier"])
        self.trans.setCurrentIndex(max(0, self.trans.findData(self.cfg["trans"]))); self.trans.blockSignals(False)
        self.fill_recs(find_reciter(self.cfg["reciter"], self.recs)["id"])
        self.reccount.setText(T("n_reciters", n=len(self.recs)))
        self.update_dl_info(); self.refresh_now(); self.preview.update()

    def dl_count(self, r):
        d = os.path.join(LIB, slug(r["folder"]))
        files = [os.path.join(d, x) for x in os.listdir(d) if x.endswith(".mp3")] if os.path.isdir(d) else []
        return len(files), sum(os.path.getsize(x) for x in files) / 1e6

    def fill_recs(self, select_id=None):
        if select_id is None and self.reclist.currentItem():
            select_id = self.reclist.currentItem().data(Qt.UserRole)["id"]
        self.reclist.clear()
        for r in self.recs:
            it = QListWidgetItem(f"{r['en']} {r['ar']} {r['style']}")
            it.setData(Qt.UserRole, r); it.setData(Qt.UserRole + 1, self.dl_count(r)[0])
            self.reclist.addItem(it)
            if r["id"] == select_id: self.reclist.setCurrentItem(it)
        self.filter_recs(self.search.text())
        if self.reclist.currentItem(): self.reclist.scrollToItem(self.reclist.currentItem(), QListWidget.PositionAtCenter)

    def fill_lib(self):
        self.lib.clear()
        for r in self.recs:
            n, mb = self.dl_count(r)
            if n:
                name = r["ar"] if rtl() else (r["en"] or r["ar"])
                it = QListWidgetItem(f"{name}      " + T("lib_item", n=n, mb=f"{mb:.0f}"))
                it.setData(Qt.UserRole, r); self.lib.addItem(it)
        if not self.lib.count():
            it = QListWidgetItem(T("nothing_dl")); it.setFlags(Qt.NoItemFlags); self.lib.addItem(it)

    def lib_select(self, it):
        r = it.data(Qt.UserRole)
        if r: self.search.clear(); self.fill_recs(r["id"]); self.update_dl_info()

    def filter_recs(self, q):
        q = q.strip()
        for i in range(self.reclist.count()):
            it = self.reclist.item(i); self.reclist.setRowHidden(i, bool(q) and not name_match(q, it.text()))

    def surah_changed(self, *_):
        n = self.surah.currentData()
        if n:
            self.ayah.setMaximum(n); self.ayah.setValue(1); self.ayah_to.setMaximum(n); self.ayah_to.setValue(0)
        self.show_surah_info()

    def show_surah_info(self):
        i = self.surah.currentIndex()
        if not (0 <= i < len(self.sur)): return
        s = self.sur[i]
        self.surah.lineEdit().setCursorPosition(0)
        self.surah_ar.setText(s["name"])
        self.surah_meta.setText(T("surah_meta", meaning=s["englishNameTranslation"], ayahs=s["numberOfAyahs"],
                                  place=T("meccan" if s["revelationType"] == "Meccan" else "medinan")))
        if hasattr(self, "b_one"):
            self.b_one.setText(T("dl_one", name=s["name"].replace("سُورَةُ ", "") if rtl() else s["englishName"]))

    def rec(self):
        it = self.reclist.currentItem()
        return it.data(Qt.UserRole) if it else (find_reciter(self.cfg["reciter"], self.recs) if self.recs else None)

    # ---------- actions ----------
    def style_values(self):
        return dict(font=self.font.currentFont().family(), size=self.size.value(),
                    tr_font=self.trfont.currentFont().family(), tr_scale=self.trscale.value(),
                    color=self.color.color, outline=self.outline.color, outline_w=self.outw.value(),
                    bg=self.bg.isChecked(), bg_color=self.bgcolor.color, bg_alpha=self.bgalpha.value(),
                    pos="top" if self.posgroup.checkedId() == 1 else "bottom", margin=self.margin.value(),
                    max_lines=self.maxlines.value(), max_width=self.maxwidth.value(), tr_lines=self.trlines.value())

    def recite_values(self):
        r = self.rec()
        d = dict(trans=self.trans.currentData() or "", speed=round(self.speed.value() / 100, 2),
                 volume=self.volume.value(), mode=self.MODES[self.modeg.checkedId()],
                 autonext=self.autonext.isChecked(), word_sync=self.wordsync.isChecked(), loop=self.loop.isChecked(),
                 mem_advance=self.adv.currentData(), mem_per_word=self.perword.value() / 10,
                 mem_min=float(self.memmin.value()), mem_fixed=float(self.memfixed.value()),
                 mem_gap=float(self.memgap.value()), mem_repeat=self.memrep.value(), mem_hint=self.hint.currentData(),
                 hint_words=self.hintwords.value(), hint_delay=float(self.hintdelay.value()))
        if r: d["reciter"] = r["id"]
        if self.sur:
            d.update(surah=self.surah.currentIndex() + 1, ayah=self.ayah.value(), range_from=self.ayah.value(),
                     range_to=self.ayah_to.value() if self.ayah_to.value() >= self.ayah.value() else 0)
        return d

    def style_changed(self, *_):
        if hasattr(self, "preview"): self.preview.update()
        self.style_timer.start(150)

    def apply_style(self):
        update_cfg(**self.style_values()); send("restyle")

    def reset_style(self):
        d = DEFAULTS
        self.font.setCurrentFont(QFont(self.qfont)); self.trfont.setCurrentFont(QFont(d["tr_font"]))
        for wdg, k in [(self.size, "size"), (self.trscale, "tr_scale"), (self.outw, "outline_w"), (self.bgalpha, "bg_alpha"),
                       (self.margin, "margin"), (self.maxlines, "max_lines"), (self.maxwidth, "max_width"), (self.trlines, "tr_lines")]:
            wdg.setValue(d[k])
        self.color.set(d["color"]); self.outline.set(d["outline"]); self.bgcolor.set(d["bg_color"])
        self.bg.setChecked(d["bg"]); self.posgroup.button(0).setChecked(True); self.style_changed()

    def play(self):
        if not self.rec(): return
        update_cfg(**self.recite_values(), **self.style_values())
        if running() and not overlay_current(): restart_overlay()
        elif not send("play"): spawn_overlay()
        QTimer.singleShot(1200, self.refresh_now)

    def toggle_visible(self, on):
        if running():
            if overlay_current(): send("visible " + ("1" if on else "0"))
            else: restart_overlay(hidden=not on)  # an older overlay that does not know this command
        elif on:
            self.play()
        QTimer.singleShot(700, self.refresh_now)

    def play_pause(self):
        if not send("pause"): self.play()

    def stop(self):
        send("quit"); QTimer.singleShot(600, self.refresh_now)

    def restart(self):
        update_cfg(**self.recite_values(), **self.style_values())
        g, page = self.geometry(), self.stack.currentIndex()
        apply_app_theme(QApplication.instance())
        w = UI(page); w.setGeometry(g); w.show(); WINDOWS.append(w)
        self.close(); self.deleteLater()
        if self in WINDOWS: WINDOWS.remove(self)

    def change_lang(self, *_):
        update_cfg(ui_lang=self.langbox.currentData()); QTimer.singleShot(0, self.restart)

    def change_theme(self, t):
        update_cfg(theme=t); QTimer.singleShot(0, self.restart)

    def change_ui_font(self):
        update_cfg(ui_font=self.uifont.currentFont().family()); QTimer.singleShot(0, self.restart)

    def refresh_now(self):
        c, live = load_cfg(), running()
        shown = live and c.get("visible", True)
        self.showsw.blockSignals(True); self.showsw.setChecked(shown); self.showsw.blockSignals(False)
        self.pill.setObjectName("pillOn" if live else "pillOff")
        self.pill.setText(("●  " + (T("live") if shown else T("hidden_pill"))) if live else ("○  " + T("off_pill")))
        self.pill.style().unpolish(self.pill); self.pill.style().polish(self.pill)
        if getattr(self, "_pp_live", None) != live:
            self._pp_live = live
            self.ppbtn.setIcon(icon("pause" if live else "play", C["ON"], mirror=False))
        if self.sur:
            s = self.sur[c["surah"] - 1]
            r = find_reciter(c["reciter"], self.recs) if self.recs else None
            self.np_name.setText(s["name"].replace("سُورَةُ ", "") if rtl() else f"{s['englishName']}  ·  {s['name'].replace('سُورَةُ ', '')}")
            sub = T("np_ayah", a=c["ayah"], n=s["numberOfAyahs"]) + "  ·  " + T("mode_" + c["mode"])
            if r and c["mode"] == "recite": sub += "  ·  " + (r["ar"] if rtl() else (r["en"] or r["ar"]))
            self.np_sub.setText(sub)

    def update_dl_info(self):
        r = self.rec()
        if not r or not hasattr(self, "dlname"): return
        n, mb = self.dl_count(r)
        self.dlname.setText(r["ar"] if rtl() else (r["en"] or r["ar"]))
        style = r["style"].replace("Rewayat ", "").replace(" A'n ", " ʿan ")
        self.dlsub.setText(f"{r['en']}   ·   {style}" if rtl() else f"{style}   ·   {r['ar']}")
        self.dlsub.setAlignment((Qt.AlignRight if rtl() else Qt.AlignLeft) | Qt.AlignAbsolute | Qt.AlignVCenter)
        self.st_n.setText(f"{n}<span style='font-size:11pt;color:{C['MUTED']}'> / {r['count']}</span>")
        self.st_mb.setText(f"{mb:.0f}")
        if not self.dl_busy: self.prog.setRange(0, r["count"]); self.prog.setValue(n)

    def download(self, nums):
        r = self.rec()
        if not r or self.dl_busy: return
        self.dl_busy, self.cancel = True, False
        for b in (self.b_all, self.b_one): b.setEnabled(False)
        self.b_cancel.setEnabled(True)
        trans = self.trans.currentData() or ""
        self.prog.setRange(0, len(nums)); self.prog.setValue(0)

        def work():
            fails = 0
            for i, s in enumerate(nums):
                if self.cancel: break
                dst = local_audio(r, s)
                try:
                    if not os.path.exists(dst):
                        download_file(r["folder"] + f"{s:03d}.mp3", dst,
                                      lambda got, tot: self.bus.dl.emit(i, len(nums), T("dl_progress", s=s,
                                          mb=f"{got / 1e6:.1f}" + (f" / {tot / 1e6:.1f}" if tot else ""))),
                                      lambda: self.cancel)
                    load_surah(s, r, trans)  # cache text + timings for offline use
                    try: word_fracs(s, r)
                    except Exception: pass
                except InterruptedError:
                    break
                except Exception as e:
                    fails += 1; self.bus.dl.emit(i, len(nums), T("dl_failed", s=s, err=e))
                self.bus.dl.emit(i + 1, len(nums), "saved")
            self.bus.dl.emit(-1, len(nums), T("dl_cancelled") if self.cancel else
                             (T("dl_done_fail", n=fails) if fails else T("dl_done")))
        threading.Thread(target=work, daemon=True).start()

    def on_dl(self, i, n, msg):
        if msg != "saved": self.dlstatus.setText(msg)
        if i < 0:
            self.dl_busy = False
            for b in (self.b_all, self.b_one): b.setEnabled(True)
            self.b_cancel.setEnabled(False)
            self.fill_recs(); self.fill_lib(); self.update_dl_info()
            return
        self.prog.setValue(i)
        if msg == "saved":
            r = self.rec()
            if r:
                k, mb = self.dl_count(r)
                self.st_n.setText(f"{k}<span style='font-size:11pt;color:{C['MUTED']}'> / {r['count']}</span>"); self.st_mb.setText(f"{mb:.0f}")

    def open_folder(self):
        os.makedirs(LIB, exist_ok=True); subprocess.Popen(["xdg-open", LIB])

    def delete_dl(self):
        it = self.lib.currentItem()
        r = (it.data(Qt.UserRole) if it else None) or self.rec()
        if not r: return
        d = os.path.join(LIB, slug(r["folder"]))
        if not os.path.isdir(d): return
        if QMessageBox.question(self, T("delete_title"), T("delete_q", name=r["ar"] if rtl() else (r["en"] or r["ar"]))) \
                != QMessageBox.Yes:
            return
        for x in os.listdir(d): os.unlink(os.path.join(d, x))
        os.rmdir(d); self.fill_recs(); self.fill_lib(); self.update_dl_info()


# ---------------------------------------------------------------- main
def main():
    if len(sys.argv) > 1 and sys.argv[1] == "ui":
        app = QApplication(sys.argv); app.setApplicationName("Quran Overlay"); app.setDesktopFileName("quran-subs")
        register_fonts(); apply_app_theme(app)
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        w = UI(); w.show(); WINDOWS.append(w)

        def scheme_changed(*_):
            if load_cfg().get("theme", "system") == "system" and WINDOWS: WINDOWS[-1].restart()
        try: app.styleHints().colorSchemeChanged.connect(scheme_changed)
        except Exception: pass
        app.exec(); return

    ap = argparse.ArgumentParser()
    ap.add_argument("--surah", type=int); ap.add_argument("--ayah", type=int)
    ap.add_argument("--mode", choices=["recite", "memorize", "manual"])
    ap.add_argument("--size", type=int)
    ap.add_argument("--hidden", action="store_true", help="start with the verses hidden")
    a = ap.parse_args()
    kw = {k: v for k, v in vars(a).items() if v is not None and k != "hidden"}
    if "surah" in kw and "ayah" not in kw: kw["ayah"] = 1
    if "surah" in kw: kw.update(range_from=kw["ayah"], range_to=0)
    if kw: update_cfg(**kw)
    if running():
        print("Already running. Use: quran-overlay.sh quit"); return
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")  # XWayland: always-on-top + click-through on GNOME
    app = QApplication(sys.argv)
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    w = Overlay()
    app.aboutToQuit.connect(w.stop_audio)
    app.exec()
    try: os.unlink(SOCK)
    except OSError: pass


if __name__ == "__main__":
    main()
