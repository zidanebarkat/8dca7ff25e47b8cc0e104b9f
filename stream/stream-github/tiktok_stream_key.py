#!/usr/bin/env python3
"""
tiktok_stream_key.py — Cookie-based stream key generator

Loads tiktok.com/tiktokv.com cookies from a JSON file and uses
the Metasec signer to call webcast/room/create/.

Usage:
    python tiktok_stream_key.py cookies.json

The cookies file should be a JSON array of cookie objects with
'name', 'value', and optionally 'domain'.
"""

import hashlib
import json
import sys
import time
import urllib.parse
from pathlib import Path

PROJECT_ROOT = Path("/home/dev/code_test/test")
METASEC_PATH = PROJECT_ROOT / "tiktok-api" / "Mobile"
SIGNERS_PATH = PROJECT_ROOT / "TikTokStreamKeyGenerator"

if str(SIGNERS_PATH) not in sys.path:
    sys.path.insert(0, str(SIGNERS_PATH))
if str(METASEC_PATH) not in sys.path:
    sys.path.insert(0, str(METASEC_PATH))

from Libs.domain_routing import build_common_headers, get_synced_unix_seconds, resolve_webcast_base_url
from Libs.signers import TikTokSigners
from Libs.device_gen import build_live_studio_browser_version


def main():
    if len(sys.argv) < 2:
        print("Usage: python tiktok_stream_key.py <cookies.json>")
        sys.exit(1)

    cookie_file = sys.argv[1]
    if not Path(cookie_file).exists():
        print(f"[!] Cookies file not found: {cookie_file}")
        sys.exit(1)

    with open(cookie_file) as f:
        cookies_list = json.load(f)

    cookie_dict = {c["name"]: c["value"] for c in cookies_list}
    print(f"[*] Loaded {len(cookies_list)} cookies")
    print(f"[*] sessionid:    {'\u2713' if 'sessionid' in cookie_dict else '\u2717'}")
    print(f"[*] sessionid_ss: {'\u2713' if 'sessionid_ss' in cookie_dict else '\u2717'}")
    print(f"[*] sid_tt:       {'\u2713' if 'sid_tt' in cookie_dict else '\u2717'}")

    from curl_cffi import requests
    s = requests.Session(impersonate="chrome")
    s.headers.update(build_common_headers(s))

    for c in cookies_list:
        s.cookies.set(c["name"], c["value"], domain=c.get("domain", ".tiktokv.com"))

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

    title = "Live Stream"
    data = {
        "title": title,
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

    body_encoded = urllib.parse.urlencode(data, doseq=True, quote_via=urllib.parse.quote)
    x_ss_stub = hashlib.md5(body_encoded.encode()).hexdigest()

    base_url = resolve_webcast_base_url(s)
    create_endpoint = base_url + "webcast/room/create/"
    print(f"[*] Using base URL: {base_url}")

    actual_url = create_endpoint + "?" + "&".join(f"{k}={v}" for k, v in params.items())
    timestamp = get_synced_unix_seconds()

    print("[*] Getting TikTok API signatures...")
    try:
        sig_headers = TikTokSigners.signature_headers(
            timestamp, aid="8311", params=params, x_ss_stub=x_ss_stub,
            device_id=device_id, url=actual_url,
        )
        print(f"[*] Signatures obtained")
    except Exception as e:
        print(f"[!] Signature failed: {e}")
        sys.exit(1)

    s.headers.update({
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "pragma": "no-cache",
        "cache-control": "no-cache",
        "x-ss-stub": x_ss_stub,
        **sig_headers,
    })
    if priority_region:
        s.headers["x-tt-store-region"] = priority_region

    print("[*] Creating live room...")
    try:
        r = s.post(
            create_endpoint,
            params=params,
            data=data,
            timeout=30,
        )
        resp = r.json()

        if r.status_code == 200 and resp.get("status_code") == 0:
            stream_data = resp["data"]
            stream_url = stream_data["stream_url"]["rtmp_push_url"]
            share_url = stream_data["share_url"]
            split_idx = stream_url.rfind("/")
            base_stream_url = stream_url[:split_idx]
            stream_key = stream_url[split_idx + 1:]

            print()
            print("=" * 60)
            print("  \u2713 STREAM KEY GENERATED!")
            print("=" * 60)
            print(f"\n  Server URL: {base_stream_url}")
            print(f"  Stream Key: {stream_key}")
            print(f"  Full RTMP:  {stream_url}")
            print(f"  Share URL:  {share_url}")
            print()
            print("  OBS Settings -> Stream:")
            print(f"    Service: Custom...")
            print(f"    Server:  {base_stream_url}")
            print(f"    Key:     {stream_key}")
            print()
            print("  Stream stays live for ~6 hours. End from TikTok LIVE Producer.")

            result = {
                "server_url": base_stream_url,
                "stream_key": stream_key,
                "rtmp_url": stream_url,
                "share_url": share_url,
            }
            with open("stream_key.json", "w") as f:
                json.dump(result, f, indent=2)
            print("[*] Saved to stream_key.json")

            try:
                import pyperclip
                pyperclip.copy(stream_key)
                print("[*] Stream key copied to clipboard!")
            except ImportError:
                pass
        else:
            msg = resp.get("data", {}).get("prompts") or resp.get("data", {}).get("message") or str(resp)
            print(f"[!] API error (code={resp.get('status_code')}): {msg}")
            print(f"    {json.dumps(resp, indent=2)[:1000]}")

    except Exception as e:
        print(f"[!] Request failed: {e}")


if __name__ == "__main__":
    main()
