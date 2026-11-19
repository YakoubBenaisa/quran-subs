#!/bin/sh
# Inside a Flatpak sandbox (e.g. VS Code)? Run on the host instead.
if [ -f /.flatpak-info ]; then exec flatpak-spawn --host "$0" "$@"; fi
exec python3 "$(dirname "$(readlink -f "$0")")/overlay.py" "$@"
