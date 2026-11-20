#!/bin/sh
# Adds global GNOME shortcuts for the Quran overlay (keeps your existing custom shortcuts).
exec "$(dirname "$(readlink -f "$0")")/quran-overlay.sh" setup-shortcuts
