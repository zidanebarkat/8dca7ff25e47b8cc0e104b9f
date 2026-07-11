#!/usr/bin/env bash
set -e

WORKDIR="$(cd "$(dirname "$0")" && pwd)"
OUTPUT="${1:-$WORKDIR/test_output.mp4}"
DURATION="${2:-15}"

cleanup() {
  echo "=== Cleanup ==="
  kill $HTTP_PID 2>/dev/null || true
  kill $CHROME_PID 2>/dev/null || true
  kill $X_PID 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT

# === 1. Create test background video if needed ===
if [ ! -f "$WORKDIR/brb.mp4" ]; then
  echo "=== Creating test background (brb.mp4) ==="
  ffmpeg -f lavfi -i "color=c=blue:s=1920x1080:d=60:r=30" \
    -f lavfi -i "anullsrc=r=44100:cl=mono" \
    -vf "drawtext=text='TEST BACKGROUND':fontsize=48:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2" \
    -shortest -y "$WORKDIR/brb.mp4"
fi

echo "file $WORKDIR/brb.mp4" > "$WORKDIR/concat.txt"
echo "Local Test Stream" > "$WORKDIR/overlay.txt"

# === 2. Xvfb ===
echo "=== Starting Xvfb :99 (400x600) ==="
Xvfb :99 -screen 0 400x600x24 &
X_PID=$!
sleep 2
xsetroot -display :99 -solid "#00ff00"

# === 3. HTTP server ===
echo "=== HTTP server on :9999 ==="
python3 -m http.server --directory "$WORKDIR" 9999 &
HTTP_PID=$!
sleep 1

# === 4. Chromium ===
OVURL="http://127.0.0.1:9999/chat_overlay.html?channel=zed-bx"
echo "=== Chromium ($OVURL) ==="
DISPLAY=:99 chromium-browser --no-sandbox --disable-gpu \
  --disable-extensions --disable-dev-shm-usage --no-first-run \
  --window-size=400,600 --window-position=0,0 --app="$OVURL" &
CHROME_PID=$!
sleep 8

# === 5. FFmpeg capture ===
FONT="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

BEVELED="drawtext=textfile=$WORKDIR/overlay.txt:reload=1:fontfile=$FONT:fontsize=54:fontcolor=0x1a0b2e:x=(w-text_w)/2+5:y=(h-text_h)/2+5,drawtext=textfile=$WORKDIR/overlay.txt:reload=1:fontfile=$FONT:fontsize=54:fontcolor=0x3a1f5e:x=(w-text_w)/2+3:y=(h-text_h)/2+3,drawtext=textfile=$WORKDIR/overlay.txt:reload=1:fontfile=$FONT:fontsize=54:fontcolor=0x6b3f96:x=(w-text_w)/2+1:y=(h-text_h)/2+1,drawtext=textfile=$WORKDIR/overlay.txt:reload=1:fontfile=$FONT:fontsize=54:fontcolor=0xC9A2FF:box=1:boxcolor=0x0a0512@0.6:boxborderw=26:bordercolor=0x1a0b2e:borderw=2:x=(w-text_w)/2:y=(h-text_h)/2:shadowcolor=black@0.85:shadowx=6:shadowy=6"

VF="[0:v]scale=1920:1080,$BEVELED[main];[2:v]scale=400:-1,colorkey=0x00ff00:0.2:0.0[over];[main][over]overlay=20:main_h-overlay_h-20[out]"

echo "=== Capturing $DURATION sec → $OUTPUT ==="
ffmpeg -nostdin -re -stream_loop -1 -i "$WORKDIR/brb.mp4" \
  -f concat -safe 0 -i "$WORKDIR/concat.txt" \
  -f x11grab -framerate 30 -video_size 400x600 -i :99.0 \
  -filter_complex "$VF" -map '[out]' -map 1:a \
  -c:v libx264 -preset ultrafast -b:v 2000k -c:a aac -b:a 96k \
  -t "$DURATION" -y "$OUTPUT"

echo "=== Done ==="
echo "Play $OUTPUT to verify:"
echo "  - Background video (blue) with centered beveled text"
echo "  - Browser chat overlay at bottom-left (green keyed out)"
echo ""
echo "To test changes: edit chat_overlay.html or restream.yml, then re-run this script."
