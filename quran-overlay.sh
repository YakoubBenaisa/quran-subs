#!/bin/sh
# Launcher for Quran Companion. Inside a Flatpak sandbox (e.g. VS Code)? Run on the host instead.
if [ -f /.flatpak-info ]; then exec flatpak-spawn --host "$0" "$@"; fi
cd "$(dirname "$(readlink -f "$0")")" && exec python3 -m quran_companion "$@"
