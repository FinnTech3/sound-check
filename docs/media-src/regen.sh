#!/usr/bin/env bash
# Rebuilds every image and clip in docs/ and agensi/media/ from real runs of the two scripts.
# Needs: Python 3.10+ with Pillow, Node with Playwright (set PW_ROOT to a folder whose node_modules has it if it is
# not installed next to this file), and ffmpeg. Takes about a minute. The sounds are deterministic, so the numbers on
# the images only change if the scripts change.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# the clip runs the shipped scripts from an empty folder, which is also how an agent runs them
demo=/tmp/sc-demo
rm -rf "$demo" && mkdir "$demo"
cp "$root"/agensi/sound-check/scripts/*.py "$demo/"

python3 "$here/record.py" "$here/demo.spec.json" "$work/demo.cast.json"
node "$here/termcast.mjs" "$work/demo.cast.json" "$root/docs/demo.gif" "$root/docs/demo.mp4"
rm -f "$demo"/*.wav
python3 "$here/record.py" "$here/still.spec.json" "$work/still.cast.json"
node "$here/termcast.mjs" "$work/still.cast.json" "$work/clipping-terminal.png" --still

python3 "$here/make_charts.py" "$work/pages"
cp "$root/agensi/media/logo.png" "$work/pages/"
node "$here/render.mjs" "$work/pages/sync.html" "$work/sync-strip.png" 2
node "$here/render.mjs" "$work/pages/clipping.html" "$work/clipping.png" 2
node "$here/render.mjs" "$work/pages/presets.html" "$work/presets.png" 2
node "$here/render.mjs" "$work/pages/social.html" "$work/social-preview.png" 1

python3 "$here/shrink.py" 128 "$work/sync-strip.png" "$work/clipping.png" "$work/presets.png" "$work/clipping-terminal.png"
cp "$work/sync-strip.png" "$work/clipping.png" "$work/presets.png" "$work/clipping-terminal.png" "$work/social-preview.png" "$root/docs/"
cp "$work/sync-strip.png" "$root/agensi/media/screenshot-1.png"
cp "$work/clipping.png" "$root/agensi/media/screenshot-2.png"
cp "$work/presets.png" "$root/agensi/media/screenshot-3.png"
ls -l "$root/docs" "$root/agensi/media"
