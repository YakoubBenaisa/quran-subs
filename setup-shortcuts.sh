#!/bin/sh
# Adds global GNOME shortcuts for the Quran overlay (keeps your existing custom shortcuts).
S="$(dirname "$(readlink -f "$0")")/quran-overlay.sh"
base=/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings
schema=org.gnome.settings-daemon.plugins.media-keys
list=$(gsettings get $schema custom-keybindings | sed "s/@as //; s/^\[//; s/\]$//")
i=0
add(){ p="$base/quran$i/"; k="$schema.custom-keybinding:$p"
  gsettings set "$k" name "Quran: $1"; gsettings set "$k" command "$S $2"; gsettings set "$k" binding "$3"
  case "$list" in *"'$p'"*) ;; *) list="$list${list:+, }'$p'";; esac; i=$((i+1)); }
add "on/off"  toggle  "<Super><Alt>q"
add next      next    "<Super><Alt>Right"
add prev      prev    "<Super><Alt>Left"
add pause     pause   "<Super><Alt>space"
add hide      hide    "<Super><Alt>h"
add bigger    bigger  "<Super><Alt>Up"
add smaller   smaller "<Super><Alt>Down"
gsettings set $schema custom-keybindings "[$list]"
echo "Shortcuts added. Super+Alt+S = settings, Super+Alt+Q = start/stop."
