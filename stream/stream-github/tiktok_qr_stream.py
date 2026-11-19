#!/usr/bin/env python3
"""
tiktok_qr_stream.py — QR login → live room creation → stream key

Uses the same passport SDK signing approach as TikTok LIVE Studio.
Step 1: Request QR code from api16-normal-*.tiktokv.com/passport/web/get_qrcode/
Step 2: Display QR as URL/terminal image for user to scan with TikTok app
Step 3: Poll api16-normal-*.tiktokv.com/passport/web/check_qrconnect/ until scanned
Step 4: Extract tiktokv.com session cookies
Step 5: Use Metasec signer to call webcast/room/create/
Step 6: Print RTMP server URL + stream key + share URL
"""

import argparse
import hashlib
import json
import os
import random
import secrets
import string
import sys
import time
import urllib.parse
from pathlib import Path

PASSPORT_APP_KEY = "884c28a44b61b78f9d837fc8b0967178"
PASSPORT_WEB_SDK_VERSION = "2.1.9"
LIVE_STUDIO_AID = 8311
METASEC_PATH = Path("/home/dev/code_test/test/tiktok-api/Mobile")
SIGNERS_PATH = Path("/home/dev/code_test/test/TikTokStreamKeyGenerator")

if str(SIGNERS_PATH) not in sys.path:
    sys.path.insert(0, str(SIGNERS_PATH))
if str(METASEC_PATH) not in sys.path:
    sys.path.insert(0, str(METASEC_PATH))

from metasec import Metasec


def md5(s):
    return hashlib.md5(s.encode()).hexdigest()


def _passport_stringify_value(value):
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    return str(value)


def _passport_sorted_string(values, limit=-1):
    ignored = {"sign", "qs", "isResend", "next", "baseURL", "extra_params"}
    keys = sorted(
        str(key)
        for key, value in values.items()
        if value is not None and str(key) not in ignored
    )
    if limit >= 0:
        keys = keys[:limit]
    parts = []
    for key in keys:
        parts.append(f"{key}={_passport_stringify_value(values.get(key))}")
    return "&".join(parts), keys


def _passport_xor5_qs(keys):
    raw = ",".join(keys).encode("utf-8")
    return "".join(f"{byte ^ 5:02x}" for byte in raw)


def _passport_sdk_signature(params, data=None, app_key=PASSPORT_APP_KEY):
    if not app_key:
        return {}
    param_string, signed_keys = _passport_sorted_string(params or {}, limit=10)
    body_string, _ = _passport_sorted_string(data or {}, limit=-1)
    base = f"{param_string}&{body_string}&app_key={app_key}"
    return {
        "sign": hashlib.md5(base.encode("utf-8")).hexdigest(),
        "qs": _passport_xor5_qs(signed_keys),
    }


def _apply_passport_sdk_signature(params, data=None):
    signed = dict(params or {})
    signed.pop("sign", None)
    signed.pop("qs", None)
    signed.update(_passport_sdk_signature(signed, data=data))
    return signed


def _dedupe_hosts(hosts):
    seen = set()
    out = []
    for host in hosts:
        host = str(host or "").strip()
        if host and host not in seen:
            seen.add(host)
            out.append(host)
    return out


def _random_qr_client_secret(length=8):
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _inject_qr_client_secret(qrcode_index_url, client_secret):
    if not qrcode_index_url or not client_secret:
        return qrcode_index_url
    decoded = urllib.parse.unquote(str(qrcode_index_url))
    base, separator, query = decoded.partition("?")
    if not separator:
        return qrcode_index_url
    values = urllib.parse.parse_qs(query, keep_blank_values=True)
    next_url = (values.get("next_url") or [""])[0]
    if not next_url:
        return qrcode_index_url
    joiner = "&" if "?" in next_url else "?"
    values["next_url"] = [f"{next_url}{joiner}client_secret={urllib.parse.quote(client_secret)}"]
    return base + "?" + urllib.parse.urlencode(values, doseq=True)


def _qrcode_png_base64(value):
    if not value:
        return ""
    try:
        import io
        import qrcode
        image = qrcode.make(value)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        import base64
        return base64.b64encode(buffer.getvalue()).decode("ascii")
    except Exception:
        return ""


def _encode_form_body(data):
    if data is None:
        return b""
    if isinstance(data, bytes):
        return data
    if isinstance(data, bytearray):
        return bytes(data)
    if isinstance(data, str):
        return data.encode()
    return urllib.parse.urlencode(data, doseq=True, quote_via=urllib.parse.quote).encode()


def _make_x_ss_stub(data):
    body = _encode_form_body(data)
    return hashlib.md5(body).hexdigest() if body else None


def _build_ticket_guard_headers():
    return {
        "tt-ticket-guard-public-key": "BHTyDu4GfY+Se8QoOlL22ARkOv4aLE5LBCk8eSiJ6K5N5m8Wg3cPeVYWVYNDrJ3hsRmaVCgNl/AKbMW67VBievw=",
        "tt-ticket-guard-version": "2",
        "tt-ticket-guard-web-version": "1",
        "tt-ticket-guard-iteration-version": "0",
    }


def get_synced_unix_seconds():
    return int(time.time())


def resolve_api_host_candidates(session=None, timeout=12):
    candidates = [
        "api16-normal-c-alisg.tiktokv.com",
        "api16-normal-no1a.tiktokv.eu",
        "api16-normal-useast8.tiktokv.us",
        "api16-normal-useast5.tiktokv.us",
    ]
    return _dedupe_hosts(candidates)


def generate_device_id() -> str:
    return str(random.randint(10000000000000000000, 99999999999999999999))


def qr_login_step1(session) -> dict:
    candidate_hosts = resolve_api_host_candidates(session)
    for host in candidate_hosts:
        url = f"https://{host}/passport/web/get_qrcode/"
        device_id = generate_device_id()
        verify_fp = f"verify_{device_id}"
        params = _apply_passport_sdk_signature({
            "next": "https://www.tiktok.com",
            "device_id": device_id,
            "aid": str(LIVE_STUDIO_AID),
            "account_sdk_source": "web",
            "sdk_version": PASSPORT_WEB_SDK_VERSION,
            "verifyFp": verify_fp,
        })
        headers = {
            "accept": "application/json, text/javascript",
            "content-type": "application/x-www-form-urlencoded",
            "referer": "https://www.tiktok.com/ucenter_web/live_studio/login",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) TikTokLIVEStudio/1.27.0 Chrome/136.0.7103.59 Electron/36.4.0-alpha.17 TTElectron/36.4.0-alpha.17 Safari/537.36",
            ** _build_ticket_guard_headers(),
            "x-ss-stub": _make_x_ss_stub(None) or "",
        }
        try:
            r = session.get(url, params=params, headers=headers, impersonate="chrome", timeout=20)
            payload = r.json()
            data_payload = payload.get("data", {}) if isinstance(payload, dict) else {}
            token = data_payload.get("token")
            qrcode_index_url = data_payload.get("qrcode_index_url") or ""
            qrcode_b64 = data_payload.get("qrcode") or ""
            if not token or not (qrcode_index_url or qrcode_b64):
                continue
            client_secret = _random_qr_client_secret()
            patched_qrcode_index_url = _inject_qr_client_secret(qrcode_index_url, client_secret)
            patched_qrcode_b64 = _qrcode_png_base64(patched_qrcode_index_url)
            data_payload = dict(data_payload)
            data_payload["qrcode_index_url_original"] = qrcode_index_url
            data_payload["qrcode_index_url"] = patched_qrcode_index_url or qrcode_index_url
            data_payload["clientSecret"] = client_secret
            data_payload["domain"] = host
            if patched_qrcode_b64:
                data_payload["qrcode"] = patched_qrcode_b64
            return data_payload, device_id
        except Exception:
            continue
    raise RuntimeError("QR login setup failed: no host responded")


def qr_login_step2(session, qr_token: str, device_id: str, domain: str, max_attempts: int = 90) -> dict:
    candidate_hosts = [domain] + resolve_api_host_candidates(session)
    for host in candidate_hosts:
        url = f"https://{host}/passport/web/check_qrconnect/"
        verify_fp = f"verify_{device_id}"
        params = _apply_passport_sdk_signature({
            "next": "https://www.tiktok.com",
            "token": qr_token,
            "multi_login": "1",
            "device_id": device_id,
            "aid": str(LIVE_STUDIO_AID),
            "account_sdk_source": "web",
            "sdk_version": PASSPORT_WEB_SDK_VERSION,
            "verifyFp": verify_fp,
        })
        headers = {
            "accept": "application/json, text/javascript",
            "content-type": "application/x-www-form-urlencoded",
            "referer": "https://www.tiktok.com/ucenter_web/live_studio/login",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) TikTokLIVEStudio/1.27.0 Chrome/136.0.7103.59 Electron/36.4.0-alpha.17 TTElectron/36.4.0-alpha.17 Safari/537.36",
            ** _build_ticket_guard_headers(),
            "x-ss-stub": _make_x_ss_stub(None) or "",
        }
        for attempt in range(1, max_attempts + 1):
            try:
                r = session.get(url, params=params, headers=headers, impersonate="chrome", timeout=15)
                data = r.json()
                code = data.get("status_code", -1)
                if code == 0:
                    print(f"\n  [\u2713] QR scanned! Extracting session...")
                    return data["data"]
                elif code == 3:
                    print(f"  [*] QR expired. Need new QR.")
                    return None
                print(f"  [*] Waiting for scan... ({attempt}/{max_attempts})", end="\r")
            except Exception as e:
                print(f"\n  [!] Poll error on {host}: {e}")
            time.sleep(2)
    print()
    raise TimeoutError("QR code not scanned within timeout")


def extract_tiktokv_cookies(session) -> list:
    cookies = []
    for cookie in session.cookies.jar if hasattr(session.cookies, 'jar') else []:
        if isinstance(cookie, dict):
            cookies.append(cookie)
        else:
            cookies.append({
                "name": cookie.name,
                "value": cookie.value,
                "domain": cookie.domain or "",
                "path": cookie.path or "/",
            })
    return cookies


def load_cookies(session, cookie_file: str) -> dict:
    with open(cookie_file) as f:
        cookies_list = json.load(f)
    cookie_dict = {}
    for c in cookies_list:
        name = c.get("name", "")
        value = c.get("value", "")
        domain = c.get("domain", ".tiktokv.com")
        cookie_dict[name] = value
        session.cookies.set(name, value, domain=domain)
    return cookie_dict


def create_stream(session, title: str, cookie_dict: dict, desc: str = "", hashtags: str = "") -> dict:
    from Libs.domain_routing import build_common_headers, get_synced_unix_seconds, resolve_webcast_base_url
    from Libs.signers import TikTokSigners
    from Libs.device_gen import build_live_studio_browser_version

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

    r = session.post(
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
        return {
            "server_url": base_stream_url,
            "stream_key": stream_key,
            "rtmp_url": stream_url,
            "share_url": share_url,
        }
    else:
        msg = resp.get("data", {}).get("prompts") or resp.get("data", {}).get("message") or str(resp)
        raise RuntimeError(f"Create stream failed (code={resp.get('status_code')}): {msg}")


def print_colored(text, color="green"):
    colors = {
        "green": "\033[92m",
        "yellow": "\033[93m",
        "red": "\033[91m",
        "cyan": "\033[96m",
        "bold": "\033[1m",
        "reset": "\033[0m",
    }
    c = colors.get(color, "")
    r = colors["reset"]
    print(f"{c}{text}{r}")


def end_stream(session, cookie_dict: dict, room_id: str = "", stream_id: str = "") -> bool:
    from Libs.domain_routing import get_synced_unix_seconds, resolve_webcast_base_url
    from Libs.signers import TikTokSigners

    device_id = cookie_dict.get("device_id", "0")
    install_id = cookie_dict.get("install_id", "0")
    priority_region = cookie_dict.get("store-country-code", "")

    version = "1.27.0"
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
        "browser_version": "5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) TikTokLIVEStudio/1.27.0 Chrome/136.0.7103.59 Electron/36.4.0-alpha.17 TTElectron/36.4.0-alpha.17 Safari/537.36",
        "language": "en",
        "app_language": "en",
        "webcast_language": "en",
        "priority_region": priority_region,
        "webcast_sdk_version": version.replace(".", ""),
        "live_mode": "6",
    }

    data = {
        "status": "4",
        "room_id": room_id,
        "stream_id": stream_id,
    }

    body_encoded = urllib.parse.urlencode(data, doseq=True, quote_via=urllib.parse.quote)
    x_ss_stub = hashlib.md5(body_encoded.encode()).hexdigest()
    timestamp = get_synced_unix_seconds()

    base_url = resolve_webcast_base_url(session)
    endpoint = base_url + "webcast/room/ping/anchor/"
    actual_url = endpoint + "?" + "&".join(f"{k}={v}" for k, v in params.items())

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

    r = session.post(endpoint, params=params, data=data, timeout=30)
    resp = r.json()
    return r.status_code == 200 and resp.get("status_code") in (0, "0")


def main():
    parser = argparse.ArgumentParser(description="TikTok QR Login → Stream Key Generator")
    parser.add_argument("--title", default="Live Stream", help="Stream title")
    parser.add_argument("--desc", default="", help="Stream description")
    parser.add_argument("--hashtags", default="", help="Comma-separated hashtags (e.g. freefire,ewc2026,ffwc)")
    parser.add_argument("--scan", action="store_true", help="Display QR via terminal (requires pillow)")
    parser.add_argument("--cookies", help="Path to existing cookies JSON (skip QR login)")
    parser.add_argument("--output", help="Output file for stream key JSON (default: stream_key.json)")
    parser.add_argument("--end", action="store_true", help="End an active stream (requires --cookies and --room-id/--stream-id)")
    parser.add_argument("--room-id", help="Room ID to end (for --end)")
    parser.add_argument("--stream-id", help="Stream ID to end (for --end)")
    args = parser.parse_args()

    from curl_cffi import requests
    s = requests.Session(impersonate="chrome")
    s.headers.update({
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) TikTokLIVEStudio/1.27.0 Chrome/136.0.7103.59 Electron/36.4.0-alpha.17 TTElectron/36.4.0-alpha.17 Safari/537.36",
    })

    cookie_file = args.cookies
    if cookie_file and Path(cookie_file).exists():
        print_colored("=== Loading cookies from file ===", "cyan")
        cookie_dict = load_cookies(s, cookie_file)
        print(f"  [\u2713] Loaded {len(cookie_dict)} cookies")
    else:
        print_colored("=== TikTok QR Login ===", "cyan")
        print_colored("  Step 1: Requesting QR code...", "yellow")

        qr_data, device_id = qr_login_step1(s)
        qr_token = qr_data.get("qrcode_index_token") or qr_data.get("token")
        qr_url = qr_data.get("qrcode_url") or qr_data.get("qrcode_index_url")
        if not qr_url:
            raise RuntimeError(f"No QR URL in response: {qr_data}")

        print_colored("  [\u2713] QR code obtained!", "green")
        print(f"\n  Scan this QR code with the TikTok app:")
        print(f"  {qr_url}")
        print()

        if args.scan:
            try:
                from PIL import Image
                import qrcode
                qr_img = qrcode.make(qr_url)
                qr_img.show()
            except ImportError:
                print("  [!] Install pillow+qrcode for terminal QR display")

        print_colored("  Step 2: Waiting for scan (90s timeout)...", "yellow")
        print_colored("  (Scan the QR code above with your TikTok app)", "bold")

        domain = qr_data.get("domain", "")
        login_data = qr_login_step2(s, qr_token, device_id, domain)
        if login_data is None:
            print_colored("  [!] QR expired. Please run again.", "red")
            return

        print_colored("  [\u2713] Login successful!", "green")

        cookies_list = extract_tiktokv_cookies(s)
        cookie_dict = {}
        for c in cookies_list:
            cookie_dict[c["name"]] = c["value"]

        print(f"  sessionid:    {'\u2713' if 'sessionid' in cookie_dict else '\u2717'}")
        print(f"  sessionid_ss: {'\u2713' if 'sessionid_ss' in cookie_dict else '\u2717'}")
        print(f"  sid_tt:       {'\u2713' if 'sid_tt' in cookie_dict else '\u2717'}")

        out_file = "tiktokv_cookies.json"
        with open(out_file, "w") as f:
            json.dump(cookies_list, f, indent=2)
        print(f"  [\u2713] Saved tiktokv.com cookies to {out_file}")

    if args.end:
        print_colored("\n=== Ending Stream ===", "cyan")
        room_id = args.room_id or cookie_dict.get("room_id", "")
        stream_id = args.stream_id or cookie_dict.get("stream_id", "")
        if not room_id or not stream_id:
            print_colored("  [!] --room-id and --stream-id required (or set in cookies)", "red")
            return
        ok = end_stream(s, cookie_dict, room_id, stream_id)
        if ok:
            print_colored("  [\u2713] Stream ended!", "green")
        else:
            print_colored("  [!] Failed to end stream", "red")
        return

    print_colored("\n=== Creating Live Room ===", "cyan")
    try:
        result = create_stream(s, args.title, cookie_dict, desc=args.desc, hashtags=args.hashtags)
        print_colored("\n" + "=" * 60, "green")
        print_colored("  \u2713 STREAM KEY GENERATED!", "green")
        print_colored("=" * 60, "green")
        print(f"\n  Server URL: {result['server_url']}")
        print(f"  Stream Key: {result['stream_key']}")
        print(f"  Full RTMP:  {result['rtmp_url']}")
        print(f"  Share URL:  {result['share_url']}")
        print()
        print_colored("  OBS Settings -> Stream:", "cyan")
        print(f"    Service: Custom...")
        print(f"    Server:  {result['server_url']}")
        print(f"    Key:     {result['stream_key']}")
        print()
        print_colored("  Stream stays live for ~6 hours. End from TikTok LIVE Producer.", "yellow")
        print_colored("  Or run: python tiktok_qr_stream.py --end --cookies tiktokv_cookies.json --room-id <ID> --stream-id <ID>", "yellow")

        out = args.output or "stream_key.json"
        with open(out, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\n  [\u2713] Saved to {out}")

        try:
            import pyperclip
            pyperclip.copy(result["stream_key"])
            print("  [\u2713] Stream key copied to clipboard!")
        except ImportError:
            pass

        return result

    except RuntimeError as e:
        print_colored(f"  [!] {e}", "red")
        return None


if __name__ == "__main__":
    main()
