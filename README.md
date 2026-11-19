# Quran Companion · رفيق التلاوة

Quran verses on your screen while you work: click-through text that follows a reciter, helps you memorize, or
follows along with another recitation. Settings window in Arabic and English, light and dark.

```sh
./quran-overlay.sh ui              # settings window
./quran-overlay.sh toggle          # start / stop the on-screen verses
./quran-overlay.sh next            # also: prev pause hide bigger smaller nextsurah prevsurah quit, surah 36 [ayah]
./quran-overlay.sh install-desktop # app-menu entry
./setup-shortcuts.sh               # GNOME shortcuts (Super+Alt+…)
```

## Architecture

Imports only point downwards; `tests/test_architecture.py` enforces that the logic layers never import Qt.

| Layer | Package | Responsibility |
|---|---|---|
| Views | `settings_ui/views`, `settings_ui/widgets`, `settings_ui/theme` | Qt widgets only: build, display, forward user actions |
| View models | `settings_ui/viewmodels` | Window state and actions (catalog, playback control, downloads, language/theme) |
| Overlay | `overlay/` | `OverlayWindow` draws pages; `OverlayController` wires session ⇄ window ⇄ commands |
| IPC | `ipc/` | Typed commands, JSON wire format + plain-text form, version handshake (`hello`) |
| Playback | `playback/` | `Session` state machine; modes as strategies (`recite`, `memorize`, `manual`); `AudioPlayer` (ffplay) and `Clock` interfaces |
| Layout | `layout/` | `Paginator`: verse → pages of at most N lines (text measuring injected) |
| Data | `data/` | Source interfaces + adapters (alquran.cloud, mp3quran.net, quran.com), disk cache, downloads, `QuranRepository` |
| Core | `core/` | Models, settings (atomic store + migration), Arabic text rules, translations |

`app.py` is the composition root: it builds the object graph for each entry point.

Patterns: Repository + Adapter (data sources), Strategy (playback modes, memorize advance policies), State machine
(`Session`), Command (IPC), Observer (Qt signals / session listener), MVVM (settings window), dependency injection
(clock, player, measurer, sources are passed in, so tests use fakes).

## Adding an interface language

Copy `quran_companion/resources/lang/en.json` to e.g. `fr.json`, set `"_name"` and `"_dir"` (`"rtl"` for
right-to-left), translate the values. It appears in the language list automatically; missing keys fall back to English.

## Development

```sh
python3 -m pip install --user pytest pytest-qt ruff mypy
python3 -m pytest          # offline: uses tests/fixtures, fake clock/player, offscreen Qt
python3 -m ruff check quran_companion tests
python3 -m mypy            # logic layers
```

`tests/golden/golden.json` was recorded from the pre-refactor single-file app (`git show d36b646:overlay.py`) with
`tests/make_golden.py`; the paginator must keep reproducing it exactly.
