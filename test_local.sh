#!/usr/bin/env bash
set -e

# Local overlay test playground
# Tests Xvfb + Chromium + chat_overlay.html + FFmpeg colorkey capture
# Output: test_output.mp4 (15 seconds)
# No network/streaming accounts needed

WORKDIR="$(cd "$(dirname "$0")" && pwd)"
OUTPUT="${1:-$WORKDIR/test_output.mp4}"
DURATION="${2:-15}"

cleanup() {
  echo "Cleaning up..."
  kill $HTTP_PID 2>/dev/null || true
  kill $CHROME_PID 2>/dev/null || true
  kill $X_PID 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT

echo "=== Starting Xvfb :99 (400x600) ==="
Xvfb :99 -screen 0 400x600x24 &
X_PID=$!
sleep 2
xsetroot -display :99 -solid "#00ff00"

echo "=== Starting HTTP server for chat_overlay.html ==="
python3 -m http.server --directory "$WORKDIR" 9999 &
HTTP_PID=$!
sleep 1

OVURL="http://127.0.0.1:9999/chat_overlay.html?channel=zed-bx"
echo "=== Launching Chromium (--app mode) ==="
DISPLAY=:99 chromium-browser --no-sandbox --disable-gpu \
  --disable-extensions --disable-dev-shm-usage --no-first-run \
  --window-size=400,600 --window-position=0,0 --app="$OVURL" &
CHROME_PID=$!
sleep 8

echo "=== Capturing $DURATION seconds to $OUTPUT ==="
ffmpeg -f x11grab -framerate 30 -video_size 400x600 -i :99.0 \
  -vf "colorkey=0x00ff00:0.2:0.0,format=rgba" \
  -c:v libx264 -preset ultrafast -t "$DURATION" -y "$OUTPUT"

echo "=== Done! Play $OUTPUT to verify the overlay ==="
echo "Green background should be transparent, showing only chat messages."
