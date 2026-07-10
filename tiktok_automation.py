"""
TikTok Stream Key Automation
=============================
Run this on YOUR local computer (NOT PythonAnywhere).

It will open a browser, let you log into TikTok, save your session cookies,
navigate to LIVE Producer, generate a fresh stream key, and output it.

Usage:
    pip install playwright
    playwright install chromium
    python tiktok_automation.py [panel_url]

If panel_url is provided (e.g. https://yourname.pythonanywhere.com),
the key will be pushed to the panel automatically.

If run without arguments, just prints the key to the console.
"""

import os, json, sys, subprocess
from pathlib import Path

COOKIE_FILE = 'tiktok_cookies.json'
PANEL_URL = sys.argv[1] if len(sys.argv) > 1 else None
PUSH_URL = f"{PANEL_URL.rstrip('/')}/tiktok/push_key" if PANEL_URL else None

try:
    import requests
except ImportError:
    if PUSH_URL:
        print("Missing requests library. Install: pip install requests")
        sys.exit(1)

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Missing playwright. Install: pip install playwright && playwright install chromium")
    sys.exit(1)


def save_cookies(context):
    cookies = context.cookies()
    Path(COOKIE_FILE).write_text(json.dumps(cookies, indent=2))
    print(f"[✓] Cookies saved to {COOKIE_FILE}")


def load_cookies(context):
    path = Path(COOKIE_FILE)
    if path.exists():
        cookies = json.loads(path.read_text())
        context.add_cookies(cookies)
        print(f"[✓] Loaded {len(cookies)} cookies from {COOKIE_FILE}")
        return True
    return False


def main():
    with sync_playwright() as p:
        launch_opts = {
            'headless': False,
            'args': [
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
            ],
        }
        browser_paths = [
            ('chrome', ['/usr/bin/google-chrome', '/usr/bin/google-chrome-stable']),
            ('chromium', ['/usr/bin/chromium-browser', '/usr/bin/chromium', '/snap/bin/chromium']),
            ('brave', ['/usr/bin/brave-browser', '/snap/bin/brave', '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser']),
        ]
        found = False
        for name, paths in browser_paths:
            for path in paths:
                if os.path.exists(path):
                    launch_opts['executablePath'] = path
                    print(f"[✓] Using installed {name.capitalize()} browser: {path}")
                    found = True
                    break
            if found:
                break
        if not found:
            print("[.] Using Playwright Chromium")

        browser = p.chromium.launch(**launch_opts)
        context = browser.new_context(
            viewport={'width': 1280, 'height': 900},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
            locale='en-US',
            timezone_id='America/New_York',
        )
        page = context.new_page()

        # Remove webdriver detection
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        """)

        has_cookies = load_cookies(context)

        print("\n Opening TikTok LIVE Producer...")
        page.goto('https://livecenter.tiktok.com/producer', timeout=60000)

        if not has_cookies:
            print("\n" + "="*60)
            print(" LOGIN REQUIRED")
            print("="*60)
            print("Log into TikTok in the browser window.")
            print("After logging in, press ENTER here to continue...")
            input()
            save_cookies(context)
            page.goto('https://livecenter.tiktok.com/producer', timeout=60000)

        # Check if we're on the producer page
        if 'producer' not in page.url:
            print(f"\n[!] Not on producer page. Current URL: {page.url}")
            print("Your account may not have LIVE Producer access yet.")
            print("You need to join a Creator Network first.")
            print("See: https://toktutorials.com/list-of-agencies")
            input("\nPress ENTER to close...")
            browser.close()
            return

        # Check if the page shows "Save and Go Live" or we need to fill details
        print("\n[.] Checking LIVE Producer page...")

        try:
            page.wait_for_selector('button:has-text("Save and Go Live"), button:has-text("Go Live"), [data-e2e="live_stream_submit_btn"]', timeout=10000)
        except:
            pass

        # Try to find and fill stream title if needed
        try:
            title_input = page.wait_for_selector('input[placeholder*="title"], input[placeholder*="Title"], [data-e2e="live_title_input"] input', timeout=3000)
            if title_input:
                title_input.fill('Streaming via Panel')
                print("[✓] Filled stream title")
        except:
            print("[.] No title input found (may already be set)")

        try:
            go_live_btn = page.wait_for_selector('button:has-text("Save and Go Live"):not([disabled]), button:has-text("Go Live"):not([disabled])', timeout=5000)
            go_live_btn.click()
            print("[✓] Clicked Save and Go Live")
            page.wait_for_timeout(3000)
        except:
            print("[.] No Save and Go Live button found")

        # Try to scrape the stream key
        print("\n[.] Looking for stream key...")
        page.wait_for_timeout(2000)

        key = None
        server_url = None

        try:
            key_el = page.wait_for_selector('[data-e2e="stream_key_value"], .stream-key-value, input[readonly][value*="FB-"], input[readonly][value*="live-"]', timeout=5000)
            if key_el:
                key = key_el.input_value() if key_el.tag_name == 'input' else key_el.text_content()
        except:
            pass

        try:
            server_el = page.wait_for_selector('[data-e2e="server_url_value"], .server-url-value, input[readonly][value*="rtmp"]', timeout=3000)
            if server_el:
                server_url = server_el.input_value() if server_el.tag_name == 'input' else server_el.text_content()
        except:
            pass

        if not key:
            # Try broader selectors - look for any input with rtmp or stream key
            try:
                all_inputs = page.query_selector_all('input[readonly]')
                for inp in all_inputs:
                    val = inp.input_value()
                    if val and ('live-' in val or 'FB-' in val or 'rtmp' in val):
                        if 'rtmp' in val:
                            server_url = val
                        else:
                            key = val
            except:
                pass

        print("\n" + "="*60)
        if key:
            full_rtmp = f"rtmp://push.live.tiktok.com/live/{key}"
            print(" STREAM KEY FOUND")
            print("="*60)
            print(f" Server URL: {server_url or 'rtmp://push.live.tiktok.com/live/'}")
            print(f" Stream Key: {key}")
            print(f" Full RTMP:  {full_rtmp}")
            print("="*60)

            if PUSH_URL:
                try:
                    r = requests.post(PUSH_URL, json={'key': key}, timeout=10)
                    if r.status_code == 200 and r.json().get('ok'):
                        print(f"[✓] Key pushed to panel at {PUSH_URL}")
                    else:
                        print(f"[!] Push failed: {r.text[:200]}")
                except Exception as e:
                    print(f"[!] Push error: {e}")
        else:
            print(" COULD NOT FIND STREAM KEY")
            print("="*60)
            print("The page may not have generated credentials yet.")
            print("Try manually clicking buttons in the browser window.")
            print("Stream key usually appears after clicking 'Save and Go Live'")
            print("Press ENTER when ready to close...")
            input()

        input("\nPress ENTER to close browser...")
        browser.close()


if __name__ == '__main__':
    main()
