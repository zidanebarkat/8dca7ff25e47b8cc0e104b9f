#!/usr/bin/env python3
"""
tiktok_auto_stream.py — Cookie-based auto stream creator + FFmpeg launcher

Decodes TikTok cookies from env/file, creates a live room via Metasec signer,
and starts FFmpeg to stream to the returned RTMP URL.

Usage:
    # With cookies file
    python tiktok_auto_stream.py --cookies tiktokv_cookies.json --source <url> --title "My Stream"

    # With TIKTOK_COOKIES env var (base64-encoded JSON)
    python tiktok_auto_stream.py --source <url> --title "My Stream"
"""

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
METASEC_PATH = PROJECT_ROOT / "tiktok-api" / "Mobile"
SIGNERS_PATH = PROJECT_ROOT / "TikTokStreamKeyGenerator"

if str(SIGNERS_PATH) not in sys.path:
    sys.path.insert(0, str(SIGNERS_PATH))
if str(METASEC_PATH) not in sys.path:
    sys.path.insert(0, str(METASEC_PATH))

from Libs.domain_routing import get_synced_unix_seconds, resolve_webcast_base_url
from Libs.signers import TikTokSigners
from Libs.device_gen import build_live_studio_browser_version


def load_cookies_from_env():
    raw = os.environ.get("TIKTOK_COOKIES", "")
    if not raw:
        return None
    try:
        decoded = base64.b64decode(raw).decode()
        return json.loads(decoded)
    except Exception:
        try:
            return json.loads(raw)
        except Exception:
            return None


def load_cookies_from_file(path):
    with open(path) as f:
        return json.load(f)


def setup_session(cookies_list):
    from curl_cffi import requests
    s = requests.Session(impersonate="chrome")
    s.headers.update({
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) TikTokLIVEStudio/1.27.0 Chrome/136.0.7103.59 Electron/36.4.0-alpha.17 TTElectron/36.4.0-alpha.17 Safari/537.36",
    })
    cookie_dict = {}
    for c in cookies_list:
        name = c["name"]
        value = c["value"]
        domain = c.get("domain", ".tiktokv.com")
        cookie_dict[name] = value
        s.cookies.set(name, value, domain=domain)
    return s, cookie_dict


def create_room(session, cookie_dict, title="Live Stream", desc="", hashtags=""):
    device_id = cookie_dict.get("device_id", "0")
    install_id = cookie_dict.get("install_id", "0")
    priority_region = cookie_dict.get("store-country-code", "")

    version = "1.27.0"
    browser_version = build_live_studio_browser_version(version)

    params = {
        "aid": "8311",
        "app_name": "tiktok_live_studio",
        "device_id": device_id,
        "install_id": install_id,
        "channel": "studio",
        "version_code": version,
        "device_platform": "windows",
        "timezone_name": "Africa/Lagos",
        "screen_width": "1920",
        "screen_height": "1080",
        "browser_language": "en-US",
        "browser_platform": "Win32",
        "browser_name": "Mozilla",
        "browser_version": browser_version,
        "language": "en",
        "app_language": "en",
        "webcast_language": "en",
        "priority_region": priority_region,
        "webcast_sdk_version": version.replace(".", ""),
        "live_mode": "6",
    }

    data = {
        "title": title,
        "description": desc,
        "live_studio": "1",
        "gen_replay": "false",
        "chat_auth": "1",
        "age_restricted": "0",
        "cover_uri": "",
        "close_room_when_close_stream": "false",
        "hashtag_id": "42",
        "game_tag_id": "0",
        "game_bitrate_type": "high",
        "screenshot_cover_status": "1",
        "multi_stream_scene": "0",
        "gift_auth": "1",
        "chat_l2": "1",
        "star_comment_switch": "true",
        "multi_stream_source": "1",
        "is_group_live_session": "false",
        "open_commercial_content_toggle": "false",
        "commercial_content_promote_myself": "false",
        "commercial_content_promote_third_party": "false",
        "rtc_net_enabled": "false",
    }

    if hashtags:
        tag_list = [t.strip() for t in hashtags.split(",") if t.strip()]
        data["hash_tag"] = ",".join(tag_list)

    body_encoded = urllib.parse.urlencode(data, doseq=True, quote_via=urllib.parse.quote)
    x_ss_stub = hashlib.md5(body_encoded.encode()).hexdigest()
    timestamp = get_synced_unix_seconds()

    base_url = resolve_webcast_base_url(session)
    create_endpoint = base_url + "webcast/room/create/"

    actual_url = create_endpoint + "?" + "&".join(f"{k}={v}" for k, v in params.items())
    sig_headers = TikTokSigners.signature_headers(
        timestamp, aid="8311", params=params, x_ss_stub=x_ss_stub,
        device_id=device_id, url=actual_url,
    )

    session.headers.update({
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "pragma": "no-cache",
        "cache-control": "no-cache",
        "x-ss-stub": x_ss_stub,
        **sig_headers,
    })
    if priority_region:
        session.headers["x-tt-store-region"] = priority_region

    r = session.post(create_endpoint, params=params, data=data, timeout=30)
    resp = r.json()

    if r.status_code == 200 and resp.get("status_code") == 0:
        stream_data = resp["data"]
        stream_url = stream_data["stream_url"]["rtmp_push_url"]
        share_url = stream_data["share_url"]
        split_idx = stream_url.rfind("/")
        base_stream_url = stream_url[:split_idx]
        stream_key = stream_url[split_idx + 1:]
        return {
            "server_url": base_stream_url,
            "stream_key": stream_key,
            "rtmp_url": stream_url,
            "share_url": share_url,
        }
    else:
        msg = resp.get("data", {}).get("prompts") or resp.get("data", {}).get("message") or str(resp)
        raise RuntimeError(f"Create room failed (code={resp.get('status_code')}): {msg}")


def start_ffmpeg(source_url, rtmp_url, bitrate="6000k", audio="192k", scale="1920:1080"):
    cmd = [
        "ffmpeg", "-re",
        "-stream_loop", "-1",
        "-i", source_url,
        "-c:v", "libx264", "-preset", "veryfast", "-b:v", bitrate,
        "-vf", f"scale={scale}",
        "-c:a", "aac", "-b:a", audio,
        "-ar", "44100",
        "-f", "flv",
        "-flvflags", "no_duration_filesize",
        rtmp_url,
    ]
    print(f"[*] Starting FFmpeg: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd)
    return proc


def main():
    parser = argparse.ArgumentParser(description="TikTok auto stream (cookie-based)")
    parser.add_argument("--cookies", help="Path to tiktokv_cookies.json")
    parser.add_argument("--source", required=True, help="Source URL (YouTube, .m3u8, etc.)")
    parser.add_argument("--title", default="Live Stream", help="Stream title")
    parser.add_argument("--desc", default="", help="Description")
    parser.add_argument("--hashtags", default="", help="Comma-separated hashtags")
    parser.add_argument("--bitrate", default="6000k", help="Video bitrate")
    parser.add_argument("--audio", default="192k", help="Audio bitrate")
    parser.add_argument("--scale", default="1920:1080", help="Resolution")
    parser.add_argument("--json", action="store_true", help="Output result as JSON")
    args = parser.parse_args()

    # Load cookies
    if args.cookies:
        cookies_list = load_cookies_from_file(args.cookies)
    else:
        cookies_list = load_cookies_from_env()

    if not cookies_list:
        print("[!] No cookies provided. Run QR login first:", file=sys.stderr)
        print("    python tiktok_qr_stream.py --scan --output tiktokv_cookies.json", file=sys.stderr)
        sys.exit(1)

    print(f"[*] Loaded {len(cookies_list)} cookies")

    # Setup session and create room
    session, cookie_dict = setup_session(cookies_list)
    print(f"[*] sessionid: {'OK' if 'sessionid' in cookie_dict else 'MISSING'}")
    print(f"[*] sid_tt:    {'OK' if 'sid_tt' in cookie_dict else 'MISSING'}")

    print(f"[*] Creating TikTok live room...")
    try:
        result = create_room(session, cookie_dict, title=args.title, desc=args.desc, hashtags=args.hashtags)
    except RuntimeError as e:
        print(f"[!] {e}", file=sys.stderr)
        sys.exit(1)

    print(f"[+] Room created!")
    print(f"    Server:  {result['server_url']}")
    print(f"    Key:     {result['stream_key']}")
    print(f"    Share:   {result['share_url']}")

    if args.json:
        print(json.dumps(result))
    else:
        # Start FFmpeg and stream
        proc = start_ffmpeg(args.source, result["rtmp_url"], args.bitrate, args.audio, args.scale)
        try:
            proc.wait()
        except KeyboardInterrupt:
            proc.terminate()
            proc.wait()


if __name__ == "__main__":
    main()
