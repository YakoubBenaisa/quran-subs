#!/bin/sh
# Serves the tool on localhost (needed for the always-on-top floating window) and opens it as an app window.
cd "$(dirname "$0")"
PORT=8765
if ! (command -v ss >/dev/null && ss -ltn | grep -q ":$PORT "); then
  python3 -m http.server $PORT --bind 127.0.0.1 >/dev/null 2>&1 &
  sleep 0.7
fi
URL="http://127.0.0.1:$PORT/index.html"
for b in google-chrome google-chrome-stable microsoft-edge microsoft-edge-stable chromium chromium-browser brave-browser; do
  command -v "$b" >/dev/null && exec "$b" --app="$URL"
done
for f in com.google.Chrome com.microsoft.Edge org.chromium.Chromium com.brave.Browser; do
  flatpak info "$f" >/dev/null 2>&1 && exec flatpak run "$f" --app="$URL"
done
exec xdg-open "$URL"
