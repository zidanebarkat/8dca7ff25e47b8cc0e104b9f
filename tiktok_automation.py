import os, json, sys, re
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Missing playwright. Install: pip install playwright && playwright install chromium")
    sys.exit(1)

COOKIE_FILE = 'tiktok_cookies.json'
PANEL_URL = sys.argv[1] if len(sys.argv) > 1 else None

def get_browser():
    paths = [
        ('brave', ['/usr/bin/brave-browser', '/snap/bin/brave', '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser']),
        ('chrome', ['/usr/bin/google-chrome', '/usr/bin/google-chrome-stable']),
        ('chromium', ['/usr/bin/chromium-browser', '/usr/bin/chromium', '/snap/bin/chromium']),
    ]
    for name, ps in paths:
        for p in ps:
            if os.path.exists(p):
                return name, {'executable_path': p}
    return 'chromium', {}

def main():
    name, extra = get_browser()
    print(f"[✓] Using {name.capitalize()}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, **extra)
        context = browser.new_context(
            viewport={'width': 1280, 'height': 900},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        )
        page = context.new_page()
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        """)

        cookie_path = Path(COOKIE_FILE)
        if cookie_path.exists():
            context.add_cookies(json.loads(cookie_path.read_text()))
            print(f"[✓] Loaded cookies from {COOKIE_FILE}")

        page.goto('https://livecenter.tiktok.com/producer', timeout=60000)

        if not cookie_path.exists():
            print("\n" + "="*60)
            print(" LOGIN REQUIRED")
            print("="*60)
            print("Log into TikTok in the browser window, then press ENTER.")
            input()
            cookies = context.cookies()
            cookie_path.write_text(json.dumps(cookies, indent=2))
            print(f"[✓] Cookies saved to {COOKIE_FILE}")

        print("\n" + "="*60)
        print(" COPY YOUR STREAM KEY FROM THE BROWSER")
        print("="*60)
        print("The LIVE Producer page is open in your browser.")
        print("Look for the Stream Key / Server URL fields.")
        print("Type or paste the stream key below and press ENTER.")
        print("(leave empty to skip)")
        print("-"*60)

        key = input("Stream Key: ").strip()

        if key:
            if PANEL_URL:
                url = f"{PANEL_URL.rstrip('/')}/tiktok/push_key"
                try:
                    r = requests.post(url, json={'key': key}, timeout=10)
                    if r.status_code == 200 and r.json().get('ok'):
                        print(f"[✓] Pushed to panel at {PANEL_URL}")
                    else:
                        print(f"[!] Push failed: {r.text[:200]}")
                except Exception as e:
                    print(f"[!] Push error: {e}")
            else:
                print(f"\nStream Key: {key}")
                print(f"RTMP URL: rtmp://push.live.tiktok.com/live/{key}")
        else:
            print("[.] No key provided")

        input("\nPress ENTER to close browser...")
        browser.close()

if __name__ == '__main__':
    main()
