#!/usr/bin/env bash
set -e

WORKDIR="$(cd "$(dirname "$0")" && pwd)"
OUTPUT="${1:-$WORKDIR/test_colorkey.mp4}"
DURATION="${2:-10}"

# Create test background (blue)
echo "=== Creating test sources ==="
ffmpeg -f lavfi -i "color=c=blue:s=1920x1080:d=${DURATION}:r=30" \
  -f lavfi -i "anullsrc=r=44100:cl=mono" \
  -shortest -y "$WORKDIR/bg.mp4" 2>/dev/null

# Create synthetic browser overlay (green background with simulated chat text)
ffmpeg -f lavfi -i "color=c=green:s=400x600:d=${DURATION}:r=30" \
  -vf "drawtext=text='User1: hello world':fontsize=24:fontcolor=white:x=10:y=h-80:box=1:boxcolor=black@0.5:boxborderw=6,drawtext=text='User2: test chat':fontsize=24:fontcolor=white:x=10:y=h-50:box=1:boxcolor=black@0.5:boxborderw=6" \
  -y "$WORKDIR/simulated_chat.mp4" 2>/dev/null

echo "test overlay text" > "$WORKDIR/overlay.txt"
FONT="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

BEVELED="drawtext=textfile=$WORKDIR/overlay.txt:reload=1:fontfile=$FONT:fontsize=54:fontcolor=0x1a0b2e:x=(w-text_w)/2+5:y=(h-text_h)/2+5,drawtext=textfile=$WORKDIR/overlay.txt:reload=1:fontfile=$FONT:fontsize=54:fontcolor=0x3a1f5e:x=(w-text_w)/2+3:y=(h-text_h)/2+3,drawtext=textfile=$WORKDIR/overlay.txt:reload=1:fontfile=$FONT:fontsize=54:fontcolor=0x6b3f96:x=(w-text_w)/2+1:y=(h-text_h)/2+1,drawtext=textfile=$WORKDIR/overlay.txt:reload=1:fontfile=$FONT:fontsize=54:fontcolor=0xC9A2FF:box=1:boxcolor=0x0a0512@0.6:boxborderw=26:bordercolor=0x1a0b2e:borderw=2:x=(w-text_w)/2:y=(h-text_h)/2:shadowcolor=black@0.85:shadowx=6:shadowy=6"

# Full filter: background + beveled text, then overlay colorkey'd simulated browser chat
VF="[0:v]scale=1920:1080,$BEVELED[main];[1:v]scale=400:-1,colorkey=0x00ff00:0.2:0.0[over];[main][over]overlay=20:main_h-overlay_h-20[out]"

echo "=== Running FFmpeg filter test ==="
ffmpeg -nostdin -re -stream_loop -1 -i "$WORKDIR/bg.mp4" \
  -i "$WORKDIR/simulated_chat.mp4" \
  -filter_complex "$VF" -map '[out]' -map 0:a \
  -c:v libx264 -preset ultrafast -b:v 2000k -c:a aac -b:a 96k \
  -t "$DURATION" -y "$OUTPUT"

echo "=== Done! ==="
echo "Output: $OUTPUT"
echo "Verifies: beveled text overlay + colorkey transparency + overlay positioning"
echo ""
echo "Note: Uses synthetic chat source (no Xvfb/Chromium needed)."
echo "To test with real browser chat, run on a machine with Xvfb + chromium-browser:"
echo "  bash run_test.sh"
