#!/usr/bin/env bash
set -e

# Full pipeline test (mimics the Fallback restream step)
# Requires: test_local.sh's Xvfb + Chromium + overlay already running
# or run: bash test_local.sh test_full_output.mp4 30

WORKDIR="$(cd "$(dirname "$0")" && pwd)"
OUTPUT="${1:-$WORKDIR/test_full_output.mp4}"
DURATION="${2:-15}"

# Create a test background video (color bars + tone if none exists)
if [ ! -f "$WORKDIR/brb.mp4" ]; then
  echo "Creating test background video (brb.mp4)..."
  ffmpeg -f lavfi -i "color=c=blue:s=1920x1080:d=30,drawtext=text='TEST BACKGROUND':fontsize=48:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2" \
    -f lavfi -i "anullsrc=r=44100:cl=mono" -shortest -y "$WORKDIR/brb.mp4"
fi

# Create concat.txt (same file listed once for loopback)
echo "file $WORKDIR/brb.mp4" > "$WORKDIR/concat.txt"

# Text overlay (simulating the panel's overlay_text input)
echo "Local Test Stream" > "$WORKDIR/overlay.txt"

FONT="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
BEVELED="drawtext=textfile=$WORKDIR/overlay.txt:reload=1:fontfile=$FONT:fontsize=54:fontcolor=0x1a0b2e:x=(w-text_w)/2+5:y=(h-text_h)/2+5,drawtext=textfile=$WORKDIR/overlay.txt:reload=1:fontfile=$FONT:fontsize=54:fontcolor=0x3a1f5e:x=(w-text_w)/2+3:y=(h-text_h)/2+3,drawtext=textfile=$WORKDIR/overlay.txt:reload=1:fontfile=$FONT:fontsize=54:fontcolor=0x6b3f96:x=(w-text_w)/2+1:y=(h-text_h)/2+1,drawtext=textfile=$WORKDIR/overlay.txt:reload=1:fontfile=$FONT:fontsize=54:fontcolor=0xC9A2FF:box=1:boxcolor=0x0a0512@0.6:boxborderw=26:bordercolor=0x1a0b2e:borderw=2:x=(w-text_w)/2:y=(h-text_h)/2:shadowcolor=black@0.85:shadowx=6:shadowy=6"

VF="[0:v]scale=1920:1080,$BEVELED[main];[2:v]scale=400:-1,colorkey=0x00ff00:0.2:0.0[over];[main][over]overlay=20:main_h-overlay_h-20[out]"

echo "=== Running full pipeline FFmpeg (Fallback mode) ==="
ffmpeg -nostdin -re -stream_loop -1 -i "$WORKDIR/brb.mp4" \
  -f concat -safe 0 -i "$WORKDIR/concat.txt" \
  -f x11grab -framerate 30 -video_size 400x600 -i :99.0 \
  -filter_complex "$VF" -map '[out]' -map 1:a \
  -c:v libx264 -preset ultrafast -b:v 2000k -c:a aac -b:a 96k \
  -t "$DURATION" -y "$OUTPUT"

echo "=== Done! $OUTPUT ==="
echo "Video: background (brb.mp4) + beveled overlay text + browser chat (colorkeyed)"
