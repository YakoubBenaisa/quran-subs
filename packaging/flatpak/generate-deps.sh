#!/bin/sh
# Writes python3-deps.json (pinned PyPI sources) and fills in the ffmpeg checksum in the manifest.
# Needs: pip install requirements-parser; flatpak-pip-generator from
#   https://github.com/flatpak/flatpak-builder-tools/tree/master/pip
set -e
cd "$(dirname "$0")"
flatpak-pip-generator --runtime='org.kde.Sdk//6.9' --output python3-deps numpy yt-dlp jeepney
url=$(grep -o 'https://ffmpeg.org/releases/ffmpeg-[0-9.]*\.tar\.xz' io.github.yakoubbenaisa.QuranCompanion.yml)
sum=$(curl -sL "$url" | sha256sum | cut -d' ' -f1)
sed -i "s/sha256: SET-BY-generate-deps.sh/sha256: $sum/; s/sha256: [0-9a-f]\{64\}/sha256: $sum/" io.github.yakoubbenaisa.QuranCompanion.yml
echo "python3-deps.json written; ffmpeg sha256 $sum"
