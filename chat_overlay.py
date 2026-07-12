#!/usr/bin/env python3
"""Python-native Kick chat overlay. Renders via Pillow, writes latest frame atomically to file."""

import argparse, io, json, os, re, signal, sys, threading, time
from collections import deque
from pathlib import Path
from urllib.parse import urlencode

try:
    from curl_cffi import requests as curl_requests
except ImportError:
    curl_requests = None
import requests as std_requests
requests = curl_requests or std_requests

from PIL import Image, ImageDraw, ImageFont

parser = argparse.ArgumentParser(description='Kick chat overlay renderer')
parser.add_argument('--channel', default='zed-bx')
parser.add_argument('--overlay-path', default='/tmp/chat_overlay_frame.png')
parser.add_argument('--simulate', action='store_true')
parser.add_argument('--badge-cache', default='/tmp/chat_badges')
parser.add_argument('--emote-cache', default='/tmp/chat_emotes')
parser.add_argument('--width', type=int, default=400)
parser.add_argument('--height', type=int, default=600)
parser.add_argument('--fps', type=int, default=5)
parser.add_argument('--max-messages', type=int, default=20)
parser.add_argument('--log-file', default='', help='Log file path for debug output')
args = parser.parse_args()

if args.log_file:
    log_fh = open(args.log_file, 'a', buffering=1)
    def log(msg):
        print(msg, file=log_fh, flush=True)
        print(msg, file=sys.stderr, flush=True)
else:
    def log(msg):
        print(msg, file=sys.stderr, flush=True)

WIDTH, HEIGHT = args.width, args.height
FPS = args.fps
MAX_MSGS = args.max_messages

FONT_PATH = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
FONT_SIZE = 17
try:
    FONT = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    FONT_SM = ImageFont.truetype(FONT_PATH, 13)
    FONT_USER = ImageFont.truetype(FONT_PATH, 16)
except Exception as e:
    print(f'chat_overlay: font load error: {e}', file=sys.stderr, flush=True)
    sys.exit(1)

PUSHER_KEY = '32cbd69e4b950bf97679'
PUSHER_URL = f'wss://ws-us2.pusher.com/app/{PUSHER_KEY}?protocol=7&client=js&version=8.4.0-rc2&flash=false'

BADGE_URLS = {
    'broadcaster': 'https://files.kick.com/badges/broadcaster.png',
    'moderator':    'https://files.kick.com/badges/mod.png',
    'subscriber':   'https://files.kick.com/badges/sub.png',
    'vip':          'https://files.kick.com/badges/vip.png',
    'verified':     'https://files.kick.com/badges/verified.png',
    'founder':      'https://files.kick.com/badges/founder.png',
    'staff':        'https://files.kick.com/badges/staff.png',
    'og':           'https://files.kick.com/badges/og.png',
    'sub_gifter':   'https://files.kick.com/badges/gifter.png',
}

BADGE_SIZE = 18
EMOTE_SIZE = 24
LINE_HEIGHT = 26
PAD = 8
MSG_MARGIN = 4
messages = deque(maxlen=MAX_MSGS)
running = True

Path(args.badge_cache).mkdir(parents=True, exist_ok=True)
Path(args.emote_cache).mkdir(parents=True, exist_ok=True)

def cache_get(cache_dir, key, url):
    path = Path(cache_dir) / key
    if path.exists():
        return Image.open(path).convert('RGBA')
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            path.write_bytes(r.content)
            return Image.open(path).convert('RGBA')
    except Exception as e:
        pass
    return None

def get_badge(badge_type):
    key = f'{badge_type}.png'
    url = BADGE_URLS.get(badge_type)
    if not url:
        return None
    img = cache_get(args.badge_cache, key, url)
    if img:
        img.thumbnail((BADGE_SIZE, BADGE_SIZE), Image.LANCZOS)
    return img

def get_emote(emote_id):
    key = f'{emote_id}.png'
    url = f'https://files.kick.com/emotes/{emote_id}/fullsize'
    img = cache_get(args.emote_cache, key, url)
    if img:
        img.thumbnail((EMOTE_SIZE, EMOTE_SIZE), Image.LANCZOS)
    return img

def parse_emotes(text):
    parts = []
    last = 0
    for m in re.finditer(r'\[emote:(\d+):([^\]]+)\]', text):
        if m.start() > last:
            parts.append(('text', text[last:m.start()]))
        parts.append(('emote', m.group(1), m.group(2)))
        last = m.end()
    if last < len(text):
        parts.append(('text', text[last:]))
    return parts

def wrap_text(text, font, max_width, draw):
    words = text.split(' ')
    lines = ['']
    for word in words:
        test = f'{lines[-1]} {word}'.strip()
        bb = draw.textbbox((0, 0), test, font=font)
        w = bb[2] - bb[0]
        if w <= max_width:
            lines[-1] = test
        else:
            lines.append(word)
    return lines

def render_frame(messages, draw, font, font_sm, font_user):
    img = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    y = HEIGHT - PAD
    for msg in reversed(messages):
        username = msg.get('username', '?')
        color = msg.get('color', '#FFFFFF')
        badges = msg.get('badges', [])
        parts = msg.get('parts', [])
        reply = msg.get('reply')

        content_width = WIDTH - 2 * PAD
        line_count = 1
        current_x = PAD
        current_y = 0

        badge_imgs = []
        for bt in badges:
            bi = get_badge(bt)
            if bi:
                badge_imgs.append(bi)

        bb_user = draw.textbbox((0, 0), username, font=font_user)
        user_w = bb_user[2] - bb_user[0]
        user_h = bb_user[3] - bb_user[1]

        line_items = []
        cx = PAD
        for b in badge_imgs:
            if cx + BADGE_SIZE + 2 <= content_width:
                line_items.append(('badge', b))
                cx += BADGE_SIZE + 2
        remaining = content_width - cx
        bb_colon = draw.textbbox((0, 0), ':', font=font_sm)
        colon_w = bb_colon[2] - bb_colon[0]
        if user_w + colon_w + 4 <= remaining:
            line_items.append(('text', username, color, font_user, 0))
            line_items.append(('text', ': ', '#888888', font_sm, 0))
            cx += user_w + colon_w + 4
        else:
            uname_trunc = username
            while uname_trunc:
                bb = draw.textbbox((0, 0), uname_trunc + ':', font=font_sm)
                if bb[2] - bb[0] <= remaining - 4:
                    break
                uname_trunc = uname_trunc[:-1]
            line_items.append(('text', uname_trunc + ': ', color, font_sm, 0))

        for part in parts:
            if part[0] == 'text':
                txt = part[1]
                font_p = font
                current_font = font_p
                bb = draw.textbbox((0, 0), txt, font=current_font)
                tw = bb[2] - bb[0]
                if cx + tw <= content_width:
                    line_items.append(('text', txt, '#FFFFFF', current_font, 0))
                    cx += tw
                else:
                    remaining_w = content_width - cx
                    if remaining_w > 10:
                        for ch in txt:
                            bb = draw.textbbox((0, 0), ch, font=current_font)
                            chw = bb[2] - bb[0]
                            if cx + chw > content_width:
                                break
                            line_items.append(('text', ch, '#FFFFFF', current_font, 0))
                            cx += chw
                    break
            elif part[0] == 'emote':
                emote_id = part[1]
                emote_name = part[2]
                ei = get_emote(emote_id)
                if ei and cx + EMOTE_SIZE + 2 <= content_width:
                    line_items.append(('emote', ei))
                    cx += EMOTE_SIZE + 2
                elif cx + EMOTE_SIZE + 2 > content_width:
                    break
                else:
                    bb = draw.textbbox((0, 0), f':{emote_name}:', font=font_sm)
                    ew = bb[2] - bb[0]
                    if cx + ew <= content_width:
                        line_items.append(('text', f':{emote_name}:', '#888888', font_sm, 0))
                        cx += ew
                    else:
                        break
            else:
                break

        msg_height = LINE_HEIGHT
        if line_items:
            y -= msg_height + MSG_MARGIN
            if y < 0:
                break
            msg_bg_y = y
            msg_bg_h = msg_height

            draw.rectangle([0, msg_bg_y, WIDTH, msg_bg_y + msg_bg_h], fill=(0, 0, 0, 160))
            ix = PAD
            iy = msg_bg_y + (msg_bg_h - BADGE_SIZE) // 2
            for item in line_items:
                if item[0] == 'badge':
                    bi = item[1]
                    img.paste(bi, (ix, iy), bi)
                    ix += BADGE_SIZE + 2
                elif item[0] == 'text':
                    txt = item[1]
                    clr = item[2]
                    f = item[3]
                    draw.text((ix, msg_bg_y + (msg_bg_h - LINE_HEIGHT) // 2), txt, fill=clr, font=f)
                    bb = draw.textbbox((0, 0), txt, font=f)
                    ix += bb[2] - bb[0]
                elif item[0] == 'emote':
                    ei = item[1]
                    ey = msg_bg_y + (msg_bg_h - EMOTE_SIZE) // 2
                    img.paste(ei, (ix, ey), ei)
                    ix += EMOTE_SIZE + 2
    return img

def simulate_messages():
    test_users = [
        ('StreamFan42', '#FF9D00', ['subscriber', 'moderator']),
        ('ChatMaster', '#FFFFFF', []),
        ('KickMod', '#00FF00', ['moderator']),
        ('NewUser', '#FFFFFF', []),
        ('SubKilla', '#FF69B4', ['subscriber']),
        ('Broadcaster', '#FF0000', ['broadcaster', 'subscriber']),
    ]
    test_texts = [
        'Hey! Great stream!',
        'LOL that was funny 😂',
        'First time watching, hi everyone!',
        'Keep it up! 🔥',
        'Hello from the chat!',
        'Nice overlay setup!',
        'PogChamp!',
        'Can you [emote:37225:KEKLEO] play this song?',
        'Hello! 👋',
        'Fire in the chat [emote:37225:KEKLEO][emote:37225:KEKLEO][emote:37225:KEKLEO]',
        'Love the vibes here',
        'What game is this?',
        'This is a test of a very long message that should wrap properly on multiple lines!',
        'GG!',
        'Hello from my phone!',
    ]
    import random
    while running:
        u = random.choice(test_users)
        t = random.choice(test_texts)
        msg = {
            'username': u[0],
            'color': u[1],
            'badges': u[2],
            'parts': parse_emotes(t),
        }
        messages.append(msg)
        time.sleep(2 + random.random() * 3)

def pusher_thread_func(chatroom_id):
    import websocket
    global running
    try:
        ws = websocket.WebSocket()
        ws.settimeout(60)
        ws.connect(PUSHER_URL, origin='https://kick.com')
    except Exception as e:
        log(f'chat_overlay: pusher connect error: {e}')
        running = False
        return

    sub = json.dumps({'event': 'pusher:subscribe', 'data': {'auth': '', 'channel': f'chatrooms.{chatroom_id}.v2'}})
    ws.send(sub)

    while running:
        try:
            raw = ws.recv()
        except Exception as e:
            log(f'chat_overlay: pusher recv error: {e}')
            time.sleep(3)
            continue
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            continue
        ev = msg.get('event', '')
        if ev == 'pusher:pong':
            pass
        elif ev == 'pusher:ping':
            try:
                ws.send(json.dumps({'event': 'pusher:pong'}))
            except:
                pass
        elif ev == 'pusher:connection_established':
            ws.send(sub)
        elif ev == 'App\\Events\\ChatMessageEvent':
            try:
                data = json.loads(msg.get('data', '{}'))
            except json.JSONDecodeError:
                continue
            sender = data.get('sender', {})
            identity = sender.get('identity', {})
            badges = [b.get('type', '') for b in identity.get('badges', [])]
            color = identity.get('color', '#FFFFFF')
            content = data.get('content', '')
            chat_msg = {
                'username': sender.get('username', '?'),
                'color': color,
                'badges': badges,
                'parts': parse_emotes(content),
            }
            if data.get('type') == 'reply' and 'metadata' in data:
                meta = data['metadata']
                orig = meta.get('original_sender', {}).get('username', '')
                orig_msg = meta.get('original_message', {}).get('content', '')
                if orig and orig_msg:
                    chat_msg['reply'] = (orig, orig_msg)
            messages.append(chat_msg)
    ws.close()

def render_loop():
    overlay_path = args.overlay_path
    tmp_path = overlay_path + '.tmp'
    log(f'chat_overlay: starting render at {FPS}fps')
    img = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    frame_interval = 1.0 / FPS
    while running:
        t0 = time.monotonic()
        try:
            frame = render_frame(list(messages), draw, FONT, FONT_SM, FONT_USER)
        except Exception as e:
            log(f'chat_overlay: render_frame error: {e}')
            import traceback
            log(traceback.format_exc())
            frame = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
        try:
            frame.save(tmp_path, format='PNG')
            os.replace(tmp_path, overlay_path)
        except Exception as e:
            log(f'chat_overlay: frame write error: {e}')
        elapsed = time.monotonic() - t0
        sleep_time = frame_interval - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)

def signal_handler(signum, frame):
    global running
    running = False

if __name__ == '__main__':
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    print(f'chat_overlay: requests backend: {"curl_cffi" if curl_requests else "standard"}', file=sys.stderr, flush=True)

    chatroom_id = None
    if not args.simulate:
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            r = requests.get(f'https://kick.com/api/v2/channels/{args.channel}', headers=headers, timeout=15)
            if r.status_code == 200:
                chatroom_id = r.json().get('chatroom', {}).get('id')
            else:
                print(f'chat_overlay: API returned {r.status_code}, using fallback resolution', file=sys.stderr, flush=True)
        except Exception as e:
            log(f'chat_overlay: API error: {e}, using fallback resolution')

        if not chatroom_id:
            try:
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                r = requests.get(f'https://kick.com/api/v2/channels/{args.channel}/chatroom', headers=headers, timeout=15)
                if r.status_code == 200:
                    chatroom_id = r.json().get('id')
            except:
                pass

        if not chatroom_id:
            log('chat_overlay: could not resolve chatroom_id, falling back to simulate mode')
            args.simulate = True
        log(f'chat_overlay: resolved chatroom_id={chatroom_id}')

    log('chat_overlay: starting')
    t_pusher = None
    if args.simulate:
        t_pusher = threading.Thread(target=simulate_messages, daemon=True)
        t_pusher.start()
    else:
        t_pusher = threading.Thread(target=pusher_thread_func, args=(chatroom_id,), daemon=True)
        t_pusher.start()

    render_loop()
    log('chat_overlay: exited cleanly')
