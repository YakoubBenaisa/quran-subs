"""Quran Companion (رفيق التلاوة): Quran verses on screen while you work.

Layers (imports only point downwards):

    settings_ui / overlay      Qt views and controllers
    ipc                        commands between the settings window and the overlay
    playback                   session state machine + recite / memorize / manual modes (no Qt)
    layout                     verse pagination (no Qt; text measuring is injected)
    data                       API sources, disk cache, downloads (no Qt)
    core                       models, settings, text rules, translations (no Qt, no network)
"""

__version__ = "5.0.2"
