import os, json, sys, re, subprocess, time, socket, shutil
from pathlib import Path
import urllib.request, urllib.parse, urllib.error

PANEL_URL = sys.argv[1] if len(sys.argv) > 1 else None

def find_live_studio():
    paths = []
    if sys.platform == 'win32':
        paths = [
            os.path.expandvars(r'%LOCALAPPDATA%\TikTok LIVE Studio\TikTok LIVE Studio.exe'),
            os.path.expandvars(r'%PROGRAMFILES%\TikTok LIVE Studio\TikTok LIVE Studio.exe'),
            os.path.expandvars(r'%APPDATA%\TikTok LIVE Studio\TikTok LIVE Studio.exe'),
        ]
    elif sys.platform == 'darwin':
        paths = [
            '/Applications/TikTok LIVE Studio.app/Contents/MacOS/TikTok LIVE Studio',
            os.path.expanduser('~/Applications/TikTok LIVE Studio.app/Contents/MacOS/TikTok LIVE Studio'),
        ]
    for p in paths:
        if os.path.exists(p):
            return p
    return None

def find_obs():
    paths = []
    if sys.platform == 'win32':
        paths = [
            os.path.expandvars(r'%PROGRAMFILES%\obs-studio\bin\64bit\obs64.exe'),
            os.path.expandvars(r'%LOCALAPPDATA%\Programs\obs-studio\bin\64bit\obs64.exe'),
        ]
    elif sys.platform == 'darwin':
        paths = ['/Applications/OBS.app/Contents/MacOS/OBS']
    for p in paths:
        if os.path.exists(p):
            return p
    return None


def extract_stream_key(cookies_dict):
    """Try to hit TikTok's internal API to get stream key."""
    
    # Build a cookie string
    cookie_str = '; '.join([f"{k}={v}" for k,v in cookies_dict.items()])

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        'Cookie': cookie_str,
        'Accept': 'application/json, text/plain, */*',
        'Referer': 'https://livecenter.tiktok.com/',
        'Origin': 'https://livecenter.tiktok.com',
    }

    endpoints = [
        'https://livecenter.tiktok.com/api/live/stream_key',
        'https://livecenter.tiktok.com/api/live/stream/info',
        'https://livecenter.tiktok.com/api/live/settings',
        'https://livecenter.tiktok.com/api/live/config',
        'https://livecenter.tiktok.com/api/live/stream/key',
        'https://livecenter.tiktok.com/api/live/stream/get/url',
        'https://livecenter.tiktok.com/api/live/stream/get_key',
        'https://livecenter.tiktok.com/api/live/gets',
    ]

    for ep in endpoints:
        try:
            req = urllib.request.Request(ep, headers=headers)
            resp = urllib.request.urlopen(req, timeout=10)
            data = resp.read().decode()
            try:
                j = json.loads(data)
                if isinstance(j, dict):
                    if j.get('ok') or j.get('success') or j.get('code') == 0:
                        d = j.get('data') or j
                        for k in ['stream_key', 'key', 'streamKey', 'streamName', 'stream_url', 'pushUrl', 'push_url', 'url']:
                            if d.get(k):
                                return d[k], ep
            except:
                continue
        except:
            continue
    return None, None

def find_browser():
    if sys.platform == 'linux':
        candidates = [
            ('google-chrome', ['google-chrome', 'google-chrome-stable']),
            ('brave', ['brave-browser', '/opt/brave.com/brave/brave']),
            ('chromium', ['chromium-browser', 'chromium']),
        ]
        for name, cmds in candidates:
            for cmd in cmds:
                path = shutil.which(cmd)
                if path:
                    return name, path
                if os.path.exists(cmd):
                    return name, cmd
    elif sys.platform == 'darwin':
        candidates = [
            ('chrome', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'),
            ('brave', '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser'),
            ('chromium', '/Applications/Chromium.app/Contents/MacOS/Chromium'),
        ]
        for name, path in candidates:
            if os.path.exists(path):
                return name, path
    return None, None

def main():
    print("=" * 60)
    print("  TikTok Auto Stream Key Tool")
    print("=" * 60)
    print()

    print("[*] Step 1: Launching your browser with remote debugging port 9222...")
    print()

    bname, bpath = find_browser()
    if not bpath:
        print("[!] Could not find Chrome/Brave/Chromium on your system.")
        print("    Please launch it manually with:")
        print("      chromium-browser --remote-debugging-port=9222")
        input("\n    Press ENTER once the browser is running...")
    else:
        print(f"[*] Found {bname} at: {bpath}")
        print("[*] Checking for existing browser on port 9222...")
        already_running = False
        try:
            r = urllib.request.urlopen('http://127.0.0.1:9222/json/version', timeout=2)
            if r.status == 200:
                already_running = True
                print("[✓] Browser already running with remote debugging on port 9222")
        except:
            pass

        if not already_running:
            print("[*] Closing existing browser instances...")
            try:
                proc_name = bpath.split('/')[-1]
                subprocess.run(['pkill', '-9', '-x', proc_name], capture_output=True, timeout=10)
                time.sleep(1)
            except:
                pass
            print(f"[*] Launching {bname} with remote debugging...")
            subprocess.Popen(
                [bpath, '--remote-debugging-port=9222', '--no-first-run'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            for i in range(10):
                time.sleep(1)
                try:
                    r = urllib.request.urlopen('http://127.0.0.1:9222/json/version', timeout=2)
                    if r.status == 200:
                        print(f"[✓] Browser launched and debugger connected (port 9222)")
                        break
                except:
                    if i < 9:
                        print(f"    Waiting for browser debugger... ({i+1}/10)")
            else:
                print("[!] Could not start browser with remote debugging.")
                print("    Start it manually: braave-browser --remote-debugging-port=9222")
        print()

    print("=" * 60)
    print("  Step 2: Log into TikTok")
    print("=" * 60)
    print()
    print("  In the browser that just opened,")
    print("  go to: https://livecenter.tiktok.com")
    print("  and log into your TikTok account.")
    print()
    input("  Press ENTER once you're logged in...")

    print()
    print("=" * 60)
    print("  Step 3: Connect to your browser")
    print("=" * 60)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[!] Playwright not installed. Run:")
        print("    pip install playwright && playwright install chromium")
        sys.exit(1)

    stream_key = None
    server_url = None

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp('http://127.0.0.1:9222')
            ctx = browser.contexts[0]
            print("[✓] Connected to your browser")

            # Try to get cookies from the existing browser
            cookies = ctx.cookies()
            cookie_dict = {c['name']: c['value'] for c in cookies}
            print(f"[*] Found {len(cookies)} cookies")

        except Exception as e:
            print(f"[!] Could not connect: {e}")
            print("    Make sure Chrome is running with --remote-debugging-port=9222")
            sys.exit(1)

    print()
    print("=" * 60)
    print("  Step 4: Finding stream key...")
    print("=" * 60)
    print()

    # Try API extraction
    print("[*] Trying TikTok API endpoints...")
    key, source = extract_stream_key(cookie_dict)
    if key:
        print(f"[✓] Found stream info from: {source}")
        if key.startswith('rtmp://') or key.startswith('srt://'):
            server_url = key
        else:
            stream_key = key

    if not stream_key and not server_url:
        print()
        print("[!] Could not auto-extract stream key from API.")
        print()
        print("This is expected for most TikTok accounts.")
        print("TikTok does not provide a static stream key")
        print("unless your account is whitelisted for RTMP streaming.")
        print()
        print("Your options:")
        print()
        print("  [1] Use TikTok LIVE Studio + OBS Virtual Camera")
        print("      (recommended, works for all accounts)")
        print()
        print("  [2] Request RTMP access from TikTok")
        print("      (account must meet requirements)")
        print()
        print("  [3] Enter stream key manually (if you have one)")
        print()
    else:
        print()
        print("[✓] Found stream info:")
        if server_url:
            print(f"    Server URL: {server_url}")
        if stream_key:
            print(f"    Stream Key: {stream_key}")
        if not server_url and stream_key:
            server_url = 'rtmp://push.live.tiktok.com/live/'
        print()
        print("  [1] Push to OBS")
        print("  [2] Push to web panel" + (f" ({PANEL_URL})" if PANEL_URL else ""))
        print("  [3] Display only")
        print("  [0] Exit")
        action = input("\nChoice: ").strip()
        if action == '1':
            obs = find_obs()
            if obs:
                subprocess.Popen([obs])
            print(f"\n    In OBS Settings -> Stream:")
            print(f"    Service: Custom...")
            print(f"    Server:  {server_url}")
            print(f"    Key:     {stream_key or ''}")
            input("\n    Press ENTER when done...")
        elif action == '2':
            key = stream_key or server_url
            if key and PANEL_URL:
                url = f"{PANEL_URL.rstrip('/')}/tiktok/push_key"
                body = json.dumps({'key': key}).encode()
                try:
                    r = urllib.request.urlopen(urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'}), timeout=10)
                    if r.status == 200:
                        print("[✓] Pushed to panel")
                except:
                    print("[!] Push failed")

    print()
    print("=" * 60)
    print("  Summary")
    print("=" * 60)
    print()
    print("  For TikTok streaming:")
    print()
    print("  Option A (recommended):  OBS -> VirtualCam -> LIVE Studio")
    print("    - Launch TikTok LIVE Studio")
    print("    - Add Video Capture -> OBS Virtual Camera")
    print("    - Click Go Live in LIVE Studio")
    print()
    if stream_key:
        print("  Option B (if RTMP enabled): OBS -> TikTok directly")
        print(f"    Server: {server_url}")
        print(f"    Key:    {stream_key}")
        print()
    print("[✓] Done")

if __name__ == '__main__':
    main()
