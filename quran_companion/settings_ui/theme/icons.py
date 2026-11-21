"""Icon factory: line / filled SVG icons (mirrored for right-to-left where it matters) and glossy tiles."""
import os

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon

from ... import paths
from ...core.i18n import rtl
from .tokens import C

# 24x24 icons. LINE = stroked, FILL = solid. Media/arrow icons are mirrored for right-to-left.
LINE = {
    "book": '<path d="M2 4.5h6a4 4 0 0 1 4 4V20a3 3 0 0 0-3-3H2z"/><path d="M22 4.5h-6a4 4 0 0 0-4 4V20a3 3 0 0 1 3-3h7z"/>',
    "palette": '<path d="M12 22a10 10 0 1 1 10-10c0 2.8-2.2 4-4 4h-1.8a2 2 0 0 0-1.5 3.3A1.7 1.7 0 0 1 12 22z"/>'
               '<circle cx="7.5" cy="11" r="1.1"/><circle cx="10.5" cy="7" r="1.1"/><circle cx="15.5" cy="7.5" r="1.1"/>',
    "download": '<path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    "link": '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    "sync": '<path d="M20 11a8 8 0 0 0-14.3-4.9L4 8"/><path d="M4 4v4h4"/><path d="M4 13a8 8 0 0 0 14.3 4.9L20 16"/><path d="M20 20v-4h-4"/>',
    "film": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M10 9.5v5l4.5-2.5z"/>',
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
    d = os.path.join(paths.cache_dir(), "ui-icons", C["name"]); os.makedirs(d, exist_ok=True); return d


def _write(name, svg):
    p = os.path.join(_icon_dir(), name + ".svg")
    with open(p, "w", encoding="utf-8") as f: f.write(svg)
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
