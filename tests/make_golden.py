"""Records outputs of the pre-refactor single-file app (git d36b646) as golden data."""
import json
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, sys.argv[1])
import overlay as o
from PySide6.QtWidgets import QApplication

app = QApplication([])
qfont = o.register_fonts()
cfg = dict(o.DEFAULTS)
out = {"pages": [], "search": {}}
rec = o.find_reciter(0)
for s, n, trans, ml, mw in [(2, 282, "en.sahih", 3, 80), (2, 255, "en.sahih", 3, 80), (2, 255, "", 2, 60),
                            (1, 1, "", 3, 80), (112, 1, "en.sahih", 3, 80), (18, 10, "fr.hamidullah", 1, 50)]:
    _, items = o.surah_text(s, trans)
    c = dict(cfg, max_lines=ml, max_width=mw, trans=trans)
    a = items[n]
    pages = o.paginate(a["ar"] + " ﴿" + o.ar_digits(n) + "﴾", a["tr"], c, qfont, 1920 * mw / 100)
    fr = o.word_fracs(s, rec).get(n, {})
    out["pages"].append(dict(surah=s, ayah=n, trans=trans, max_lines=ml, max_width=mw,
        pages=[dict(lines=p["lines"], tr=p["tr"], w0=p["w0"], frac=round(p["frac"], 6),
                    word_frac=round(fr[p["w0"] + 1], 6) if (p["w0"] + 1) in fr else None) for p in pages]))
recs = o.reciters()
for q in ["ahmed bin taleb", "أحمد بن طالب", "husary", "alafasy", "afasy", "abdul basit", "sudais", "minshawi", "عبدالباسط", "maher", "zz"]:
    out["search"][q] = sorted({r["id"] for r in recs if o.name_match(q, f"{r['en']} {r['ar']} {r['style']}")})
out["tokens_2_282"] = len(o.tokens(o.surah_text(2)[1][282]["ar"]))
out["qdc_ids"] = {str(r["id"]): o.qdc_id(r) for r in recs if o.qdc_id(r)}
json.dump(out, open(sys.argv[2], "w"), ensure_ascii=False, indent=1)
print("pages", [len(p["pages"]) for p in out["pages"]], "qdc", len(out["qdc_ids"]))
