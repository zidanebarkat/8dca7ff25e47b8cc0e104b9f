from flask import Flask, request, jsonify, redirect
import os, time, json, requests, threading, subprocess

_ENV = {}

def load_env():
    env = {}
    try:
        with open('.env') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    k, _, v = line.partition('=')
                    env[k.strip()] = v.strip().strip('"').strip("'")
    except:
        pass
    return env

_ENV.update(load_env())

app = Flask(__name__)

GITHUB_TOKEN = _ENV.get('GITHUB_TOKEN', '')
GITHUB_REPO = _ENV.get('GITHUB_REPO', '')
GITHUB_OWNER = _ENV.get('GITHUB_OWNER', '')
PANEL_PASSWORD = _ENV.get('PANEL_PASSWORD', '')
current_run_id = None
config_path = 'gh_config.json'
log_buffer = []
log_lock = threading.Lock()

from functools import wraps

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not PANEL_PASSWORD:
            return f(*args, **kwargs)
        auth = request.authorization
        if auth and auth.password == PANEL_PASSWORD:
            return f(*args, **kwargs)
        return ('Unauthorized', 401, {'WWW-Authenticate': 'Basic realm="Stream Panel"'})
    return decorated

AUTH_WHITELIST = {'/preview_frame', '/preview_frame_upload'}

@app.before_request
def check_auth():
    if not PANEL_PASSWORD:
        return
    if request.path in AUTH_WHITELIST:
        return
    auth = request.authorization
    if auth and auth.password == PANEL_PASSWORD:
        return
    return ('Unauthorized', 401, {'WWW-Authenticate': 'Basic realm="Stream Panel"'})

def init_wanted():
    global wanted, yt_wanted, twt_wanted, tt_wanted, fb_wanted, kick_chill_wanted
    try:
        with open(config_path) as f:
            c = json.load(f)
            wanted = c.get('kick_wanted', False)
            yt_wanted = c.get('yt_wanted', False)
            twt_wanted = c.get('twt_wanted', False)
            tt_wanted = c.get('tt_wanted', False)
            fb_wanted = c.get('fb_wanted', False)
            fb_now_wanted = c.get('fb_now_wanted', False)
            kick_chill_wanted = c.get('kick_chill_wanted', False)
    except:
        pass

DEFAULTS = {
    'source_url': _ENV.get('SOURCE_URL', 'https://kick.com/soulzeref'),
    'output_url': _ENV.get('KICK_SRT', ''),
    'github_token': _ENV.get('GITHUB_TOKEN', ''),
    'github_owner': _ENV.get('GITHUB_OWNER', ''),
    'github_repo': _ENV.get('GITHUB_REPO', ''),
    'keepalive': False,
    'yt_url': _ENV.get('YT_URL', 'https://www.twitch.tv/kaicenat'),
    'yt_key': _ENV.get('YT_KEY', ''),
    'yt_cookies': '',
    'yt_repo': _ENV.get('YT_REPO', '8dca7ff25e47b8cc0e104b9f-yt'),
    'yt_keepalive': False,
    'twt_url': _ENV.get('TWT_URL', 'https://www.twitch.tv/kaicenat'),
    'twt_key': _ENV.get('TWT_KEY', ''),
    'twt_restream_url': '',
    'twt_repo': _ENV.get('TWT_REPO', '8dca7ff25e47b8cc0e104b9f-twt'),
    'twt_keepalive': False,
    'twt_client_id': _ENV.get('TWT_CLIENT_ID', ''),
    'twt_token': _ENV.get('TWT_TOKEN', ''),
    'tt_url': _ENV.get('TT_URL', 'https://www.twitch.tv/kaicenat'),
    'tt_key': _ENV.get('TT_KEY', ''),
    'tt_repo': _ENV.get('TT_REPO', '8dca7ff25e47b8cc0e104b9f-tt'),
    'tt_keepalive': False,
    'tt_source_duration': 1800,
    'fb_url': _ENV.get('FB_URL', 'https://www.twitch.tv/kaicenat'),
    'fb_key': _ENV.get('FB_KEY', ''),
    'fb_repo': _ENV.get('FB_REPO', '8dca7ff25e47b8cc0e104b9f-fb'),
    'fb_keepalive': False,
    'fb_now_url': '',
    'fb_now_sources': '',
    'fb_now_source_index': 0,
    'fb_now_source_duration': 1800,
    'fb_now_key': '',
    'fb_now_repo': _ENV.get('FB_NOW_REPO', '8dca7ff25e47b8cc0e104b9f-fb'),
    'fb_now_keepalive': False,
    'kick_chill_repo': _ENV.get('KICK_CHILL_REPO', '8dca7ff25e47b8cc0e104b9f-kick-chill'),
    'kick_chill_url': '',
    'kick_chill_key': '',
    'kick_chill_keepalive': False,
    'overlay_text': '',
    'browser_overlay_url': '',
    'cookies_b64': '',
    'overlay_channel': 'zed-bx',
    'kick_wanted': False,
    'yt_wanted': False,
    'twt_wanted': False,
    'tt_wanted': False,
    'fb_wanted': False,
    'fb_now_wanted': False,
    'fb_now_cookies': '',
    'fb_now_sources': '',
    'fb_now_source_index': 0,
    'fb_now_source_duration': 1800,
    'fb_now_chat_enabled': False,
    'fb_live_video_id': '',
    'fb_chat_token': '',
    'yt_chat_enabled': False,
    'youtube_api_key': '',
}

wanted = False
yt_wanted = False
twt_wanted = False
tt_wanted = False
fb_wanted = False
fb_now_wanted = False
kick_chill_wanted = False

def load_config():
    try:
        with open(config_path) as f:
            return json.load(f)
    except:
        return dict(DEFAULTS)

def save_config(cfg):
    global wanted, yt_wanted, twt_wanted, tt_wanted, fb_wanted, fb_now_wanted
    cfg['kick_wanted'] = wanted
    cfg['yt_wanted'] = yt_wanted
    cfg['twt_wanted'] = twt_wanted
    cfg['tt_wanted'] = tt_wanted
    cfg['fb_wanted'] = fb_wanted
    cfg['fb_now_wanted'] = fb_now_wanted
    with open(config_path, 'w') as f:
        json.dump(cfg, f)

def log(msg):
    with log_lock:
        ts = time.strftime('%H:%M:%S')
        log_buffer.append(f'[{ts}] {msg}')
        if len(log_buffer) > 200:
            log_buffer[:] = log_buffer[-200:]

def trigger_workflow(source_url, output_url, preview=False):
    cfg = load_config()
    token = cfg.get('github_token') or GITHUB_TOKEN
    owner = cfg.get('github_owner') or GITHUB_OWNER
    repo = cfg.get('github_repo') or GITHUB_REPO
    if not token or not owner or not repo:
        return None, None, 'Missing GitHub config'
    url = f'https://api.github.com/repos/{owner}/{repo}/actions/workflows/restream.yml/dispatches'
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github.v3+json'}
    inputs = {
        'source_url': source_url,
        'output_url': output_url,
        'overlay_text': cfg.get('overlay_text', ''),
        'browser_overlay_url': cfg.get('browser_overlay_url', ''),
        'github_token': token,
    }
    data = {'ref': 'main', 'inputs': inputs}
    r = requests.post(url, json=data, headers=headers)
    if r.status_code not in (204, 201, 200):
        return None, None, f'GitHub API error: {r.status_code} {r.text[:200]}'
    run_id = None
    if preview:
        for _ in range(15):
            time.sleep(1)
            runs_url = f'https://api.github.com/repos/{owner}/{repo}/actions/workflows/restream.yml/runs?per_page=5&event=workflow_dispatch'
            r2 = requests.get(runs_url, headers=headers)
            if r2.status_code == 200:
                for run in r2.json().get('workflow_runs', []):
                    if run['status'] in ('in_progress', 'queued', 'pending'):
                        run_id = run['id']
                        break
            if run_id:
                break
    return 'triggered', run_id, None

def trigger_yt_workflow(source_url, youtube_key):
    cfg = load_config()
    token = cfg.get('github_token') or GITHUB_TOKEN
    owner = cfg.get('github_owner') or GITHUB_OWNER
    repo = cfg.get('yt_repo') or '8dca7ff25e47b8cc0e104b9f-yt'
    if not token or not owner or not repo:
        return None, 'Missing GitHub config'
    url = f'https://api.github.com/repos/{owner}/{repo}/actions/workflows/restream.yml/dispatches'
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github.v3+json'}
    output_url = youtube_key if youtube_key.startswith('rtmp') else f'rtmp://a.rtmp.youtube.com/live2/{youtube_key}'
    cookies_b64 = cfg.get('cookies_b64', '').strip()
    if not cookies_b64 and cfg.get('yt_cookies'):
        import base64, json
        raw = cfg['yt_cookies'].strip()
        if raw.startswith('['):
            try:
                cookies = json.loads(raw)
                lines = ['# Netscape HTTP Cookie File']
                for c in cookies:
                    domain = c.get('domain', '')
                    flag = 'TRUE' if domain.startswith('.') else 'FALSE'
                    path = c.get('path', '/')
                    secure = 'TRUE' if c.get('secure', False) else 'FALSE'
                    expires = str(int(c.get('expirationDate', 0)))
                    name = c.get('name', '')
                    value = c.get('value', '')
                    httponly = '#HttpOnly_' if c.get('httpOnly', False) else ''
                    lines.append(f'{httponly}{domain}\t{flag}\t{path}\t{secure}\t{expires}\t{name}\t{value}')
                raw = '\n'.join(lines) + '\n'
            except:
                pass
        cookies_b64 = base64.b64encode(raw.encode()).decode()
    inputs = {
        'source_url': source_url,
        'output_url': output_url,
        'overlay_text': cfg.get('overlay_text', ''),
        'cookies_b64': cookies_b64,
        'github_token': token,
        'chat_enabled': 'true' if cfg.get('yt_chat_enabled') else 'false',
        'youtube_api_key': cfg.get('youtube_api_key', ''),
    }
    data = {'ref': 'main', 'inputs': inputs}
    r = requests.post(url, json=data, headers=headers)
    if r.status_code not in (204, 201, 200):
        return None, f'GitHub API error: {r.status_code} {r.text[:200]}'
    return 'triggered', None

def trigger_twt_workflow(source_url, twitch_key):
    cfg = load_config()
    token = cfg.get('github_token') or GITHUB_TOKEN
    owner = cfg.get('github_owner') or GITHUB_OWNER
    repo = cfg.get('twt_repo') or '8dca7ff25e47b8cc0e104b9f-twt'
    if not token or not owner or not repo:
        return None, 'Missing GitHub config'
    url = f'https://api.github.com/repos/{owner}/{repo}/actions/workflows/restream.yml/dispatches'
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github.v3+json'}
    output_url = twitch_key if twitch_key.startswith(('rtmp', 'srt')) else f'rtmp://live.twitch.tv/app/{twitch_key}'
    cookies_b64 = cfg.get('cookies_b64', '').strip()
    if not cookies_b64 and cfg.get('yt_cookies'):
        import base64, json
        raw = cfg['yt_cookies'].strip()
        if raw.startswith('['):
            try:
                cookies = json.loads(raw)
                lines = ['# Netscape HTTP Cookie File']
                for c in cookies:
                    domain = c.get('domain', '')
                    flag = 'TRUE' if domain.startswith('.') else 'FALSE'
                    path = c.get('path', '/')
                    secure = 'TRUE' if c.get('secure', False) else 'FALSE'
                    expires = str(int(c.get('expirationDate', 0)))
                    name = c.get('name', '')
                    value = c.get('value', '')
                    httponly = '#HttpOnly_' if c.get('httpOnly', False) else ''
                    lines.append(f'{httponly}{domain}\t{flag}\t{path}\t{secure}\t{expires}\t{name}\t{value}')
                raw = '\n'.join(lines) + '\n'
            except:
                pass
        cookies_b64 = base64.b64encode(raw.encode()).decode()
    inputs = {
        'source_url': source_url,
        'output_url': output_url,
        'overlay_text': cfg.get('overlay_text', ''),
        'browser_overlay_url': cfg.get('browser_overlay_url', ''),
        'cookies_b64': cookies_b64,
        'github_token': token,
    }
    data = {'ref': 'main', 'inputs': inputs}
    r = requests.post(url, json=data, headers=headers)
    if r.status_code not in (204, 201, 200):
        return None, f'GitHub API error: {r.status_code} {r.text[:200]}'
    return 'triggered', None

def trigger_tt_workflow(source_url, tiktok_key):
    cfg = load_config()
    token = cfg.get('github_token') or GITHUB_TOKEN
    owner = cfg.get('github_owner') or GITHUB_OWNER
    repo = cfg.get('tt_repo') or '8dca7ff25e47b8cc0e104b9f-tt'
    if not token or not owner or not repo:
        return None, 'Missing GitHub config'
    url = f'https://api.github.com/repos/{owner}/{repo}/actions/workflows/restream.yml/dispatches'
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github.v3+json'}
    output_url = tiktok_key if tiktok_key.startswith(('rtmp', 'srt')) else f'rtmp://push-fs-hsc.pull-ttok.com/ingest/{tiktok_key}'
    cookies_b64 = cfg.get('cookies_b64', '').strip()
    if not cookies_b64 and cfg.get('yt_cookies'):
        import base64, json
        raw = cfg['yt_cookies'].strip()
        if raw.startswith('['):
            try:
                cookies = json.loads(raw)
                lines = ['# Netscape HTTP Cookie File']
                for c in cookies:
                    domain = c.get('domain', '')
                    flag = 'TRUE' if domain.startswith('.') else 'FALSE'
                    path = c.get('path', '/')
                    secure = 'TRUE' if c.get('secure', False) else 'FALSE'
                    expires = str(int(c.get('expirationDate', 0)))
                    name = c.get('name', '')
                    value = c.get('value', '')
                    httponly = '#HttpOnly_' if c.get('httpOnly', False) else ''
                    lines.append(f'{httponly}{domain}\t{flag}\t{path}\t{secure}\t{expires}\t{name}\t{value}')
                raw = '\n'.join(lines) + '\n'
            except:
                pass
        cookies_b64 = base64.b64encode(raw.encode()).decode()
    inputs = {
        'source_url': source_url,
        'output_url': output_url,
        'overlay_text': cfg.get('overlay_text', ''),
        'cookies_b64': cookies_b64,
        'github_token': token,
        'source_duration': str(cfg.get('tt_source_duration', 1800)),
    }
    data = {'ref': 'main', 'inputs': inputs}
    r = requests.post(url, json=data, headers=headers)
    if r.status_code not in (204, 201, 200):
        return None, f'GitHub API error: {r.status_code} {r.text[:200]}'
    return 'triggered', None

def trigger_fb_workflow(source_url, facebook_key):
    cfg = load_config()
    token = cfg.get('github_token') or GITHUB_TOKEN
    owner = cfg.get('github_owner') or GITHUB_OWNER
    repo = cfg.get('fb_repo') or '8dca7ff25e47b8cc0e104b9f-fb'
    if not token or not owner or not repo:
        return None, 'Missing GitHub config'
    url = f'https://api.github.com/repos/{owner}/{repo}/actions/workflows/restream.yml/dispatches'
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github.v3+json'}
    output_url = facebook_key if facebook_key.startswith(('rtmp', 'srt')) else f'rtmps://live-api-s.facebook.com:443/rtmp/{facebook_key}'
    inputs = {
        'source_url': source_url,
        'output_url': output_url,
        'overlay_text': cfg.get('overlay_text', ''),
        'browser_overlay_url': cfg.get('browser_overlay_url', ''),
        'github_token': token,
    }
    data = {'ref': 'main', 'inputs': inputs}
    r = requests.post(url, json=data, headers=headers)
    if r.status_code not in (204, 201, 200):
        return None, f'GitHub API error: {r.status_code} {r.text[:200]}'
    return 'triggered', None

def trigger_fb_now_workflow(source_url, facebook_key, source_index=0, sources_b64=''):
    cfg = load_config()
    token = cfg.get('github_token') or GITHUB_TOKEN
    owner = cfg.get('github_owner') or GITHUB_OWNER
    repo = cfg.get('fb_now_repo') or '8dca7ff25e47b8cc0e104b9f-fb'
    if not token or not owner or not repo:
        return None, 'Missing GitHub config'
    url = f'https://api.github.com/repos/{owner}/{repo}/actions/workflows/restream.yml/dispatches'
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github.v3+json'}
    output_url = facebook_key if facebook_key.startswith(('rtmp', 'srt')) else f'rtmps://live-api-s.facebook.com:443/rtmp/{facebook_key}'
    cookies_b64 = cfg.get('cookies_b64', '').strip()
    if not cookies_b64:
        raw_cookies = cfg.get('fb_now_cookies', '')
        log(f'FB-Now: fb_now_cookies in config = {len(raw_cookies)} chars')
        if raw_cookies:
            import base64, json
            raw = raw_cookies.strip()
            if raw.startswith('['):
                try:
                    cookies = json.loads(raw)
                    lines = ['# Netscape HTTP Cookie File']
                    for c in cookies:
                        domain = c.get('domain', '')
                        flag = 'TRUE' if domain.startswith('.') else 'FALSE'
                        path = c.get('path', '/')
                        secure = 'TRUE' if c.get('secure', False) else 'FALSE'
                        expires = str(int(c.get('expirationDate', 0)))
                        name = c.get('name', '')
                        value = c.get('value', '')
                        httponly = '#HttpOnly_' if c.get('httpOnly', False) else ''
                        lines.append(f'{httponly}{domain}\t{flag}\t{path}\t{secure}\t{expires}\t{name}\t{value}')
                    raw = '\n'.join(lines) + '\n'
                except:
                    pass
            cookies_b64 = base64.b64encode(raw.encode()).decode()
            log(f'FB-Now: cookies_b64 = {len(cookies_b64)} chars')
    elif cookies_b64 and ('Netscape' in cookies_b64 or cookies_b64.startswith('#')):
        import base64
        cookies_b64 = base64.b64encode(cookies_b64.encode()).decode()
    inputs = {
        'source_url': source_url,
        'output_url': output_url,
        'overlay_text': cfg.get('overlay_text', ''),
        'cookies_b64': cookies_b64,
        'github_token': token,
        'source_list_b64': sources_b64,
        'source_index': str(source_index),
        'source_duration': str(cfg.get('fb_now_source_duration', 1800)),
        'chat_enabled': 'true' if cfg.get('fb_now_chat_enabled') else 'false',
        'fb_live_video_id': cfg.get('fb_live_video_id', ''),
        'fb_chat_token': cfg.get('fb_chat_token', ''),
    }
    data = {'ref': 'main', 'inputs': inputs}
    r = requests.post(url, json=data, headers=headers)
    if r.status_code not in (204, 201, 200):
        return None, f'GitHub API error: {r.status_code} {r.text[:200]}'
    return 'triggered', None

def trigger_kick_chill_workflow(source_url, kick_key):
    cfg = load_config()
    token = cfg.get('github_token') or GITHUB_TOKEN
    owner = cfg.get('github_owner') or GITHUB_OWNER
    repo = cfg.get('kick_chill_repo') or '8dca7ff25e47b8cc0e104b9f-kick-chill'
    if not token or not owner or not repo:
        return None, 'Missing GitHub config'
    url = f'https://api.github.com/repos/{owner}/{repo}/actions/workflows/stream.yml/dispatches'
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github.v3+json'}
    output_url = kick_key if kick_key.startswith(('rtmp', 'srt')) else f'rtmp://stream.kick.com/app/{kick_key}'
    cookies_b64 = cfg.get('cookies_b64', '').strip()
    raw_cookies = cfg.get('yt_cookies', '')
    if not cookies_b64 and raw_cookies:
        import base64, json
        raw = raw_cookies.strip()
        if raw.startswith('['):
            try:
                cookies = json.loads(raw)
                lines = ['# Netscape HTTP Cookie File']
                for c in cookies:
                    domain = c.get('domain', '')
                    flag = 'TRUE' if domain.startswith('.') else 'FALSE'
                    path = c.get('path', '/')
                    secure = 'TRUE' if c.get('secure', False) else 'FALSE'
                    expires = str(int(c.get('expirationDate', 0)))
                    name = c.get('name', '')
                    value = c.get('value', '')
                    httponly = '#HttpOnly_' if c.get('httpOnly', False) else ''
                    lines.append(f'{httponly}{domain}\t{flag}\t{path}\t{secure}\t{expires}\t{name}\t{value}')
                raw = '\n'.join(lines) + '\n'
            except:
                pass
        cookies_b64 = base64.b64encode(raw.encode()).decode()
    inputs = {
        'source_url': source_url,
        'output_url': output_url,
        'overlay_text': cfg.get('overlay_text', ''),
        'cookies_b64': cookies_b64,
        'github_token': token,
    }
    data = {'ref': 'main', 'inputs': inputs}
    r = requests.post(url, json=data, headers=headers)
    if r.status_code not in (204, 201, 200):
        return None, f'GitHub API error: {r.status_code} {r.text[:200]}'
    return 'triggered', None

def cancel_workflow(run_id, token, owner, repo):
    url = f'https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}/cancel'
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github.v3+json'}
    r = requests.post(url, headers=headers)
    return r.status_code in (202, 204, 200)

def get_active_run(token, owner, repo):
    url = f'https://api.github.com/repos/{owner}/{repo}/actions/workflows/restream.yml/runs?status=in_progress&per_page=1'
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github.v3+json'}
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        runs = r.json().get('workflow_runs', [])
        if runs:
            return runs[0]['id']
    return None

def keepalive_loop():
    global wanted
    while True:
        try:
            cfg = load_config()
            if wanted and cfg.get('keepalive'):
                token = cfg.get('github_token')
                owner = cfg.get('github_owner')
                repo = cfg.get('github_repo')
                if token and owner and repo:
                    run_id = get_active_run(token, owner, repo)
                    if not run_id:
                        log('Keepalive: re-triggering Kick workflow')
                        trigger_workflow(cfg['source_url'], cfg.get('output_url',''))
            elif not wanted:
                time.sleep(30)
                continue
        except Exception as e:
            log(f'Keepalive error: {e}')
        time.sleep(60)

def yt_keepalive_loop():
    global yt_wanted
    while True:
        try:
            cfg = load_config()
            if yt_wanted and cfg.get('yt_keepalive'):
                token = cfg.get('github_token')
                owner = cfg.get('github_owner')
                repo = cfg.get('yt_repo')
                if token and owner and repo:
                    run_id = get_active_run(token, owner, repo)
                    if not run_id:
                        log('YT Keepalive: re-triggering workflow')
                        trigger_yt_workflow(cfg['yt_url'], cfg.get('yt_key',''))
            elif not yt_wanted:
                time.sleep(30)
                continue
        except Exception as e:
            log(f'YT Keepalive error: {e}')
        time.sleep(60)

def twt_keepalive_loop():
    global twt_wanted
    while True:
        try:
            cfg = load_config()
            if twt_wanted and cfg.get('twt_keepalive'):
                token = cfg.get('github_token')
                owner = cfg.get('github_owner')
                repo = cfg.get('twt_repo')
                if token and owner and repo:
                    run_id = get_active_run(token, owner, repo)
                    if not run_id:
                        log('TWT Keepalive: re-triggering workflow')
                        trigger_twt_workflow(cfg['twt_url'], cfg.get('twt_key',''))
            elif not twt_wanted:
                time.sleep(30)
                continue
        except Exception as e:
            log(f'TWT Keepalive error: {e}')
        time.sleep(60)

def tt_keepalive_loop():
    global tt_wanted
    while True:
        try:
            cfg = load_config()
            if tt_wanted and cfg.get('tt_keepalive'):
                token = cfg.get('github_token')
                owner = cfg.get('github_owner')
                repo = cfg.get('tt_repo')
                if token and owner and repo:
                    run_id = get_active_run(token, owner, repo)
                    if not run_id:
                        log('TT Keepalive: re-triggering workflow')
                        trigger_tt_workflow(cfg['tt_url'], cfg.get('tt_key',''))
            elif not tt_wanted:
                time.sleep(30)
                continue
        except Exception as e:
            log(f'TT Keepalive error: {e}')
        time.sleep(60)

def fb_keepalive_loop():
    global fb_wanted
    while True:
        try:
            cfg = load_config()
            if fb_wanted and cfg.get('fb_keepalive'):
                token = cfg.get('github_token')
                owner = cfg.get('github_owner')
                repo = cfg.get('fb_repo')
                if token and owner and repo:
                    run_id = get_active_run(token, owner, repo)
                    if not run_id:
                        log('FB Keepalive: re-triggering workflow')
                        trigger_fb_workflow(cfg['fb_url'], cfg.get('fb_key',''))
            elif not fb_wanted:
                time.sleep(30)
                continue
        except Exception as e:
            log(f'FB Keepalive error: {e}')
        time.sleep(60)

threading.Thread(target=keepalive_loop, daemon=True).start()
threading.Thread(target=yt_keepalive_loop, daemon=True).start()
threading.Thread(target=twt_keepalive_loop, daemon=True).start()
threading.Thread(target=tt_keepalive_loop, daemon=True).start()
threading.Thread(target=fb_keepalive_loop, daemon=True).start()

@app.route('/')
def index():
    return HTML_PANEL

@app.route('/config', methods=['GET', 'POST'])
def update_config():
    if request.method == 'GET':
        return jsonify(load_config())
    data = request.get_json(force=True)
    cfg = load_config()
    cfg.update(data)
    save_config(cfg)
    return jsonify({'ok': True, 'config': cfg})

@app.route('/status')
def get_status():
    cfg = load_config()
    token = cfg.get('github_token')
    owner = cfg.get('github_owner')
    repo = cfg.get('github_repo')
    live = False
    run_id = None
    if token and owner and repo:
        run_id = get_active_run(token, owner, repo)
        live = run_id is not None
    return jsonify({'live': live, 'config': cfg, 'run_id': run_id, 'keepalive': cfg.get('keepalive', False), 'wanted': wanted})

@app.route('/start')
def start_stream():
    global wanted
    cfg = load_config()
    if not cfg.get('source_url') or not cfg.get('output_url'):
        return jsonify({'ok': False, 'error': 'Missing source URL or output URL'})
    msg, run_id, err = trigger_workflow(cfg['source_url'], cfg.get('output_url',''))
    if err:
        return jsonify({'ok': False, 'error': err})
    wanted = True
    save_config(cfg)
    log('Workflow triggered')
    return jsonify({'ok': True, 'msg': msg})

@app.route('/stop')
def stop_stream():
    global wanted
    wanted = False
    cfg = load_config()
    save_config(cfg)
    token = cfg.get('github_token')
    owner = cfg.get('github_owner')
    repo = cfg.get('github_repo')
    if not token or not owner or not repo:
        return jsonify({'ok': False, 'error': 'GitHub not configured'})
    run_id = get_active_run(token, owner, repo)
    if not run_id:
        return jsonify({'ok': False, 'error': 'No active run found'})
    cancel_workflow(run_id, token, owner, repo)
    log('Workflow cancelled')
    return jsonify({'ok': True})

@app.route('/logs')
def get_logs():
    with log_lock:
        return '\n'.join(log_buffer[-100:]), 200, {'Content-Type': 'text/plain'}

def do_resolve(url, cfg):
    import subprocess
    base = ['yt-dlp', '--socket-timeout', '15']
    for fmt in [['--format', 'best'], ['--format', 'worst']]:
        try:
            r = subprocess.run(base + fmt + ['-g', url],
                capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                lines = [l.strip() for l in r.stdout.strip().split('\n') if l.strip()]
                if lines:
                    return lines[-1], False
        except:
            pass
    return None, False

@app.route('/resolve')
def resolve_source():
    cfg = load_config()
    if not cfg.get('source_url'):
        return jsonify({'ok': False, 'error': 'No source URL'}), 400
    hls, fallback = do_resolve(cfg['source_url'], cfg)
    if hls:
        return jsonify({'ok': True, 'hls': hls, 'source': cfg['source_url'], 'fallback': fallback})
    return jsonify({'ok': False, 'error': 'Not live'}), 400

@app.route('/yt/resolve')
def yt_resolve_source():
    cfg = load_config()
    url = cfg.get('yt_url')
    if not url:
        return jsonify({'ok': False, 'error': 'No source URL'}), 400
    hls, fallback = do_resolve(url, cfg)
    if hls:
        return jsonify({'ok': True, 'hls': hls, 'source': url, 'fallback': fallback})
    return jsonify({'ok': False, 'error': 'Not live'}), 400

@app.route('/upload_env', methods=['POST'])
def upload_env():
    file = request.files.get('env_file')
    if not file:
        return jsonify({'ok': False, 'error': 'No file uploaded'})
    file.save('.env')
    _ENV.clear()
    _ENV.update(load_env())
    log('.env file uploaded and loaded')
    return jsonify({'ok': True, 'msg': 'Uploaded. Reload page to apply.'})

@app.route('/update_meta')
def update_meta():
    return jsonify({'ok': True, 'results': {}})

@app.route('/yt')
def yt_index():
    return HTML_YT_PANEL

@app.route('/yt/status')
def yt_status():
    cfg = load_config()
    token = cfg.get('github_token')
    owner = cfg.get('github_owner')
    repo = cfg.get('yt_repo')
    live = False
    run_id = None
    if token and owner and repo:
        run_id = get_active_run(token, owner, repo)
        live = run_id is not None
    return jsonify({'live': live, 'config': cfg, 'run_id': run_id, 'keepalive': cfg.get('yt_keepalive', False), 'wanted': yt_wanted})

@app.route('/yt/start')
def yt_start():
    global yt_wanted
    cfg = load_config()
    if not cfg.get('yt_url'):
        return jsonify({'ok': False, 'error': 'Missing source URL'})
    if not cfg.get('yt_key'):
        return jsonify({'ok': False, 'error': 'Missing YouTube stream key'})
    msg, err = trigger_yt_workflow(cfg['yt_url'], cfg.get('yt_key',''))
    if err:
        return jsonify({'ok': False, 'error': err})
    yt_wanted = True
    log('YouTube workflow triggered')
    save_config(cfg)
    return jsonify({'ok': True, 'msg': msg})

@app.route('/yt/stop')
def yt_stop():
    global yt_wanted
    yt_wanted = False
    cfg = load_config()
    save_config(cfg)
    token = cfg.get('github_token')
    owner = cfg.get('github_owner')
    repo = cfg.get('yt_repo')
    if not token or not owner or not repo:
        return jsonify({'ok': False, 'error': 'GitHub not configured'})
    run_id = get_active_run(token, owner, repo)
    if not run_id:
        return jsonify({'ok': False, 'error': 'No active run found'})
    cancel_workflow(run_id, token, owner, repo)
    log('YouTube workflow cancelled')
    return jsonify({'ok': True})

@app.route('/twitch')
def twt_index():
    return HTML_TWT_PANEL

@app.route('/twitch/status')
def twt_status():
    cfg = load_config()
    token = cfg.get('github_token')
    owner = cfg.get('github_owner')
    repo = cfg.get('twt_repo')
    live = False
    run_id = None
    if token and owner and repo:
        run_id = get_active_run(token, owner, repo)
        live = run_id is not None
    return jsonify({'live': live, 'config': cfg, 'run_id': run_id, 'keepalive': cfg.get('twt_keepalive', False), 'wanted': twt_wanted})

@app.route('/twitch/start')
def twt_start():
    global twt_wanted
    cfg = load_config()
    if not cfg.get('twt_url'):
        return jsonify({'ok': False, 'error': 'Missing source URL'})
    key = cfg.get('twt_restream_url', '') or cfg.get('twt_key', '')
    if not key:
        return jsonify({'ok': False, 'error': 'Missing stream key or Restream URL'})
    msg, err = trigger_twt_workflow(cfg['twt_url'], key)
    if err:
        return jsonify({'ok': False, 'error': err})
    twt_wanted = True
    log('Twitch workflow triggered')
    save_config(cfg)
    return jsonify({'ok': True, 'msg': msg})

@app.route('/twitch/stop')
def twt_stop():
    global twt_wanted
    twt_wanted = False
    cfg = load_config()
    save_config(cfg)
    token = cfg.get('github_token')
    owner = cfg.get('github_owner')
    repo = cfg.get('twt_repo')
    if not token or not owner or not repo:
        return jsonify({'ok': False, 'error': 'GitHub not configured'})
    run_id = get_active_run(token, owner, repo)
    if not run_id:
        return jsonify({'ok': False, 'error': 'No active run found'})
    cancel_workflow(run_id, token, owner, repo)
    log('Twitch workflow cancelled')
    return jsonify({'ok': True})

@app.route('/twitch/fetch_key')
def twt_fetch_key():
    cfg = load_config()
    cid = cfg.get('twt_client_id')
    token = cfg.get('twt_token')
    if not cid or not token:
        return jsonify({'ok': False, 'error': 'Missing Twitch Client ID or OAuth Token'})
    try:
        r = requests.get('https://api.twitch.tv/helix/users',
            headers={'Authorization': f'Bearer {token}', 'Client-Id': cid})
        if r.status_code != 200:
            return jsonify({'ok': False, 'error': f'User fetch failed: {r.status_code}'})
        uid = r.json()['data'][0]['id']
        r2 = requests.get(f'https://api.twitch.tv/helix/streams/key?broadcaster_id={uid}',
            headers={'Authorization': f'Bearer {token}', 'Client-Id': cid})
        if r2.status_code != 200:
            return jsonify({'ok': False, 'error': f'Key fetch failed: {r2.status_code}'})
        key = r2.json()['data'][0]['stream_key']
        cfg['twt_key'] = key
        save_config(cfg)
        return jsonify({'ok': True, 'key': key})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@app.route('/twitch/resolve')
def twt_resolve_source():
    cfg = load_config()
    url = cfg.get('twt_url')
    if not url:
        return jsonify({'ok': False, 'error': 'No source URL'}), 400
    hls, fallback = do_resolve(url, cfg)
    if hls:
        return jsonify({'ok': True, 'hls': hls, 'source': url, 'fallback': fallback})
    return jsonify({'ok': False, 'error': 'Not live'}), 400

@app.route('/tiktok')
def tt_index():
    return HTML_TT_PANEL

@app.route('/tiktok/status')
def tt_status():
    cfg = load_config()
    token = cfg.get('github_token')
    owner = cfg.get('github_owner')
    repo = cfg.get('tt_repo')
    live = False
    run_id = None
    if token and owner and repo:
        run_id = get_active_run(token, owner, repo)
        live = run_id is not None
    return jsonify({'live': live, 'config': cfg, 'run_id': run_id, 'keepalive': cfg.get('tt_keepalive', False), 'wanted': tt_wanted})

@app.route('/tiktok/start')
def tt_start():
    global tt_wanted
    cfg = load_config()
    if not cfg.get('tt_url'):
        return jsonify({'ok': False, 'error': 'Missing source URL'})
    if not cfg.get('tt_key'):
        return jsonify({'ok': False, 'error': 'Missing TikTok stream key'})
    msg, err = trigger_tt_workflow(cfg['tt_url'], cfg.get('tt_key',''))
    if err:
        return jsonify({'ok': False, 'error': err})
    tt_wanted = True
    log('TikTok workflow triggered')
    save_config(cfg)
    return jsonify({'ok': True, 'msg': msg})

@app.route('/tiktok/stop')
def tt_stop():
    global tt_wanted
    tt_wanted = False
    cfg = load_config()
    save_config(cfg)
    token = cfg.get('github_token')
    owner = cfg.get('github_owner')
    repo = cfg.get('tt_repo')
    if not token or not owner or not repo:
        return jsonify({'ok': False, 'error': 'GitHub not configured'})
    run_id = get_active_run(token, owner, repo)
    if not run_id:
        return jsonify({'ok': False, 'error': 'No active run found'})
    cancel_workflow(run_id, token, owner, repo)
    log('TikTok workflow cancelled')
    return jsonify({'ok': True})

@app.route('/tiktok/resolve')
def tt_resolve_source():
    cfg = load_config()
    url = cfg.get('tt_url')
    if not url:
        return jsonify({'ok': False, 'error': 'No source URL'}), 400
    hls, fallback = do_resolve(url, cfg)
    if hls:
        return jsonify({'ok': True, 'hls': hls, 'source': url, 'fallback': fallback})
    return jsonify({'ok': False, 'error': 'Not live'}), 400

@app.route('/facebook')
def fb_index():
    return HTML_FB_PANEL

@app.route('/facebook/status')
def fb_status():
    cfg = load_config()
    token = cfg.get('github_token')
    owner = cfg.get('github_owner')
    repo = cfg.get('fb_repo')
    live = False
    run_id = None
    if token and owner and repo:
        run_id = get_active_run(token, owner, repo)
        live = run_id is not None
    return jsonify({'live': live, 'config': cfg, 'run_id': run_id, 'keepalive': cfg.get('fb_keepalive', False), 'wanted': fb_wanted})

@app.route('/facebook/start')
def fb_start():
    global fb_wanted
    cfg = load_config()
    if not cfg.get('fb_url'):
        return jsonify({'ok': False, 'error': 'Missing source URL'})
    if not cfg.get('fb_key'):
        return jsonify({'ok': False, 'error': 'Missing Facebook stream key'})
    msg, err = trigger_fb_workflow(cfg['fb_url'], cfg.get('fb_key',''))
    if err:
        return jsonify({'ok': False, 'error': err})
    fb_wanted = True
    log('Facebook workflow triggered')
    save_config(cfg)
    return jsonify({'ok': True, 'msg': msg})

@app.route('/facebook/stop')
def fb_stop():
    global fb_wanted
    fb_wanted = False
    cfg = load_config()
    save_config(cfg)
    token = cfg.get('github_token')
    owner = cfg.get('github_owner')
    repo = cfg.get('fb_repo')
    if not token or not owner or not repo:
        return jsonify({'ok': False, 'error': 'GitHub not configured'})
    run_id = get_active_run(token, owner, repo)
    if not run_id:
        return jsonify({'ok': False, 'error': 'No active run found'})
    cancel_workflow(run_id, token, owner, repo)
    log('Facebook workflow cancelled')
    return jsonify({'ok': True})

@app.route('/facebook/resolve')
def fb_resolve_source():
    cfg = load_config()
    url = cfg.get('fb_url')
    if not url:
        return jsonify({'ok': False, 'error': 'No source URL'}), 400
    hls, fallback = do_resolve(url, cfg)
    if hls:
        return jsonify({'ok': True, 'hls': hls, 'source': url, 'fallback': fallback})
    return jsonify({'ok': False, 'error': 'Not live'}), 400

@app.route('/fb-now')
def fb_now_index():
    return HTML_FB_NOW_PANEL

@app.route('/fb-now/status')
def fb_now_status():
    cfg = load_config()
    token = cfg.get('github_token')
    owner = cfg.get('github_owner')
    repo = cfg.get('fb_now_repo')
    live = False
    run_id = None
    if token and owner and repo:
        run_id = get_active_run(token, owner, repo)
        live = run_id is not None
    return jsonify({'live': live, 'config': cfg, 'run_id': run_id, 'keepalive': cfg.get('fb_now_keepalive', False), 'wanted': fb_now_wanted, 'source_index': cfg.get('fb_now_source_index', 0), 'source_count': len([u.strip() for u in cfg.get('fb_now_sources', '').splitlines() if u.strip()]) or (1 if cfg.get('fb_now_url') else 0)})

@app.route('/fb-now/start')
def fb_now_start():
    global fb_now_wanted
    import base64
    cfg = load_config()
    sources_text = cfg.get('fb_now_sources', '').strip()
    if sources_text:
        sources = [u.strip() for u in sources_text.splitlines() if u.strip()]
    else:
        src = cfg.get('fb_now_url', '')
        sources = [src] if src else []
    if not sources:
        return jsonify({'ok': False, 'error': 'No source URLs'})
    if not cfg.get('fb_now_key'):
        return jsonify({'ok': False, 'error': 'Missing Facebook stream key'})
    sources_b64 = base64.b64encode('\n'.join(sources).encode()).decode()
    source_index = cfg.get('fb_now_source_index', 0) or 0
    if source_index >= len(sources):
        source_index = 0
    current_url = sources[source_index]
    log(f'FB-Now: playing source {source_index+1}/{len(sources)}: {current_url[:80]}')
    msg, err = trigger_fb_now_workflow(current_url, cfg.get('fb_now_key',''), source_index, sources_b64)
    if err:
        return jsonify({'ok': False, 'error': err})
    fb_now_wanted = True
    cfg['fb_now_source_index'] = source_index
    save_config(cfg)
    return jsonify({'ok': True, 'msg': msg, 'source_index': source_index, 'total_sources': len(sources)})

@app.route('/fb-now/stop')
def fb_now_stop():
    global fb_now_wanted
    fb_now_wanted = False
    cfg = load_config()
    save_config(cfg)
    token = cfg.get('github_token')
    owner = cfg.get('github_owner')
    repo = cfg.get('fb_now_repo')
    if not token or not owner or not repo:
        return jsonify({'ok': False, 'error': 'GitHub not configured'})
    run_id = get_active_run(token, owner, repo)
    if not run_id:
        return jsonify({'ok': False, 'error': 'No active run found'})
    cancel_workflow(run_id, token, owner, repo)
    log('FB-Now workflow cancelled')
    return jsonify({'ok': True})

@app.route('/fb-now/next')
def fb_now_next():
    global fb_now_wanted
    import base64
    cfg = load_config()
    sources_text = cfg.get('fb_now_sources', '').strip()
    if sources_text:
        sources = [u.strip() for u in sources_text.splitlines() if u.strip()]
    else:
        return jsonify({'ok': False, 'error': 'No source queue'})
    if not cfg.get('fb_now_key'):
        return jsonify({'ok': False, 'error': 'Missing Facebook stream key'})
    current_index = cfg.get('fb_now_source_index', 0) or 0
    next_index = current_index + 1
    if next_index >= len(sources):
        if cfg.get('fb_now_keepalive'):
            next_index = 0
            log('FB-Now: queue finished, looping from start')
        else:
            log('FB-Now: queue finished, stopping')
            fb_now_wanted = False
            save_config(cfg)
            return jsonify({'ok': True, 'msg': 'Queue finished'})
    sources_b64 = base64.b64encode('\n'.join(sources).encode()).decode()
    current_url = sources[next_index]
    log(f'FB-Now: advancing to source {next_index+1}/{len(sources)}: {current_url[:80]}')
    msg, err = trigger_fb_now_workflow(current_url, cfg.get('fb_now_key',''), next_index, sources_b64)
    if err:
        return jsonify({'ok': False, 'error': err})
    fb_now_wanted = True
    cfg['fb_now_source_index'] = next_index
    save_config(cfg)
    return jsonify({'ok': True, 'msg': msg, 'source_index': next_index, 'total_sources': len(sources)})

@app.route('/fb-now/resolve')
def fb_now_resolve_source():
    cfg = load_config()
    url = cfg.get('fb_now_url')
    if not url:
        return jsonify({'ok': False, 'error': 'No source URL'}), 400
    hls, fallback = do_resolve(url, cfg)
    if hls:
        return jsonify({'ok': True, 'hls': hls, 'source': url, 'fallback': fallback})
    return jsonify({'ok': False, 'error': 'Not live'}), 400

@app.route('/chat')
def chat_index():
    return HTML_CHAT_PANEL

@app.route('/preview')
def preview_page():
    cfg = load_config()
    token = cfg.get('github_token') or GITHUB_TOKEN
    owner = cfg.get('github_owner') or GITHUB_OWNER
    repo = cfg.get('github_repo') or GITHUB_REPO
    if not token or not owner or not repo:
        return '<html><body style="background:#0d1117;color:#c9d1d9;font-family:sans-serif;padding:40px"><h1>Preview Unavailable</h1><p>Configure GitHub credentials first.</p><p><a href="/" style="color:#58a6ff">← Back to panel</a></p></body></html>'
    # Check if already running
    existing = get_active_preview_run(token, owner, repo)
    if existing:
        return redirect(f'/preview_status_page?run_id={existing}&owner={owner}&repo={repo}')
    msg, run_id, err = trigger_workflow(cfg.get('source_url',''), cfg.get('output_url',''), preview=True)
    if err:
        return f'<html><body style="background:#0d1117;color:#c9d1d9;font-family:sans-serif;padding:40px"><h1>Preview Error</h1><p>{err}</p><p><a href="/" style="color:#58a6ff">← Back to panel</a></p></body></html>'
    # Save preview run_id
    with open('preview_run_id.txt', 'w') as f:
        f.write(str(run_id or ''))
    return redirect(f'/preview_status_page?run_id={run_id}&owner={owner}&repo={repo}')

@app.route('/preview_status_page')
def preview_status_page():
    run_id = request.args.get('run_id')
    owner = request.args.get('owner')
    repo = request.args.get('repo')
    if not run_id or not owner or not repo:
        return '<html><body style="background:#0d1117;color:#c9d1d9;font-family:sans-serif;padding:40px"><h1>Invalid preview link</h1><p><a href="/" style="color:#58a6ff">← Back to panel</a></p></body></html>'
    return PREVIEW_HTML.replace('%RUN_ID%', run_id).replace('%OWNER%', owner).replace('%REPO%', repo)

@app.route('/preview/status')
def preview_status():
    run_id = request.args.get('run_id')
    owner = request.args.get('owner')
    repo = request.args.get('repo')
    if not run_id or not owner or not repo:
        return jsonify({'ok': False, 'error': 'Missing params'})
    cfg = load_config()
    token = cfg.get('github_token') or GITHUB_TOKEN
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github.v3+json'}
    r = requests.get(f'https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}', headers=headers)
    if r.status_code != 200:
        return jsonify({'ok': False, 'error': f'API error: {r.status_code}'})
    data = r.json()
    return jsonify({
        'ok': True,
        'status': data.get('status'),
        'conclusion': data.get('conclusion'),
        'done': data.get('status') == 'completed',
        'html_url': data.get('html_url', ''),
    })

@app.route('/preview/go_live')
def preview_go_live():
    cfg = load_config()
    token = cfg.get('github_token') or GITHUB_TOKEN
    owner = cfg.get('github_owner') or GITHUB_OWNER
    repo = cfg.get('github_repo') or GITHUB_REPO
    if not token or not owner or not repo:
        return jsonify({'ok': False, 'error': 'Missing GitHub config'})
    # Cancel preview run
    try:
        with open('preview_run_id.txt') as f:
            prev_run_id = f.read().strip()
        if prev_run_id:
            cancel_workflow(int(prev_run_id), token, owner, repo)
    except:
        pass
    # Also cancel any other active preview runs
    existing = get_active_preview_run(token, owner, repo)
    if existing:
        cancel_workflow(existing, token, owner, repo)
    # Now trigger real Go Live
    msg, run_id, err = trigger_workflow(cfg.get('source_url',''), cfg.get('output_url',''))
    if err:
        return jsonify({'ok': False, 'error': err})
    global wanted
    wanted = True
    save_config(cfg)
    return jsonify({'ok': True, 'msg': msg})

def get_active_preview_run(token, owner, repo):
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github.v3+json'}
    url = f'https://api.github.com/repos/{owner}/{repo}/actions/workflows/restream.yml/runs?per_page=5&event=workflow_dispatch'
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        for run in r.json().get('workflow_runs', []):
            if run['status'] in ('in_progress', 'queued', 'pending'):
                return run['id']
    return None

@app.route('/preview/restart')
def preview_restart():
    cfg = load_config()
    token = cfg.get('github_token') or GITHUB_TOKEN
    owner = cfg.get('github_owner') or GITHUB_OWNER
    repo = cfg.get('github_repo') or GITHUB_REPO
    existing = get_active_preview_run(token, owner, repo)
    if existing:
        cancel_workflow(existing, token, owner, repo)
    msg, run_id, err = trigger_workflow(cfg.get('source_url',''), cfg.get('output_url',''), preview=True)
    if err:
        return f'<html><body style="background:#0d1117;color:#c9d1d9;font-family:sans-serif;padding:40px"><h1>Preview Error</h1><p>{err}</p><p><a href="/" style="color:#58a6ff">← Back to panel</a></p></body></html>'
    with open('preview_run_id.txt', 'w') as f:
        f.write(str(run_id or ''))
    return redirect(f'/preview_status_page?run_id={run_id}&owner={owner}&repo={repo}')

PREVIEW_FRAME_PATH = '/tmp/preview_frame.jpg'

@app.route('/preview_frame_upload', methods=['POST'])
def preview_frame_upload():
    if 'frame' not in request.files:
        return 'no frame', 400
    f = request.files['frame']
    f.save(PREVIEW_FRAME_PATH)
    return 'ok'

@app.route('/preview_frame')
def preview_frame():
    if os.path.exists(PREVIEW_FRAME_PATH):
        return open(PREVIEW_FRAME_PATH, 'rb').read(), 200, {'Content-Type': 'image/jpeg'}
    return '', 404

PREVIEW_HTML = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Stream Preview</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0d1117;color:#c9d1d9;font-family:'Segoe UI',sans-serif;display:flex;justify-content:center;align-items:center;min-height:100vh}
.container{text-align:center;padding:20px;max-width:600px}
h1{font-size:20px;margin-bottom:16px;color:#f0f6fc}
.status-box{padding:30px;background:#161b22;border:1px solid #30363d;border-radius:8px;margin-bottom:20px}
.spinner{border:3px solid #30363d;border-top:3px solid #58a6ff;border-radius:50%;width:40px;height:40px;animation:spin 1s linear infinite;margin:20px auto}
@keyframes spin{to{transform:rotate(360deg)}}
.status-text{font-size:15px;color:#8b949e;margin-top:12px}
.status-text.running{color:#58a6ff}
.status-text.stopped{color:#f85149}
.actions{display:flex;gap:12px;justify-content:center;flex-wrap:wrap;margin-top:20px}
.btn{display:inline-flex;align-items:center;gap:8px;padding:10px 24px;border:none;border-radius:6px;font-size:15px;font-weight:600;cursor:pointer;text-decoration:none}
.btn-green{background:#238636;color:#fff}
.btn-green:hover{background:#2ea043}
.btn-red{background:#da3633;color:#fff}
.btn-red:hover{background:#f85149}
.btn-grey{background:#21262d;color:#c9d1d9;border:1px solid #30363d}
.btn-grey:hover{background:#30363d}
.btn:disabled{opacity:.5;cursor:not-allowed}
.note{font-size:13px;color:#8b949e;margin-top:16px;line-height:1.5}
.preview-image{max-width:100%;border-radius:6px;border:1px solid #30363d;margin-top:16px;background:#000}
.preview-image.hidden{display:none}
</style>
</head>
<body>
<div class="container">
<h1>🔍 Stream Preview</h1>
<div class="status-box" id="mainBox">
  <div class="spinner" id="spinner"></div>
  <div class="status-text running" id="statusText">Starting preview on GitHub...</div>
  <img id="previewImage" class="preview-image hidden" src="" alt="Preview output">
</div>
<div class="actions" id="actions" style="display:none">
  <button class="btn btn-red" id="btnGoLive" onclick="goLive()">▶ Looks good, Go Live!</button>
  <a class="btn btn-grey" href="/preview/restart">🔄 Restart Preview</a>
  <a class="btn btn-grey" href="/">← Back to panel</a>
</div>
<div class="note" id="note">
  Preview runs the full pipeline (Python chat overlay + FFmpeg) on GitHub.<br>
  It outputs to /dev/null — same setup as a real stream, just no destination.<br>
  Click <b>Go Live</b> when ready — preview stops and real stream starts.
</div>
</div>
<script>
const RUN_ID = '%RUN_ID%';
const OWNER = '%OWNER%';
const REPO = '%REPO%';

let goLiveClicked = false;
let staleRetries = 0;
async function poll() {
  if (goLiveClicked) return;
  const elapsed = Math.round((Date.now() - startTime) / 1000);
  try {
    const r = await fetch(`/preview/status?run_id=${RUN_ID}&owner=${OWNER}&repo=${REPO}`);
    const d = await r.json();
    if (!d.ok) {
      if (elapsed < 20) {
        document.getElementById('statusText').textContent = 'Waiting for workflow to appear... (' + elapsed + 's)';
        setTimeout(poll, 2000);
        return;
      }
      document.getElementById('statusText').textContent = 'Error: ' + (d.error||'unknown');
      document.getElementById('spinner').style.display = 'none';
      return;
    }
    if (d.done) {
      if (elapsed < 20 && staleRetries < 5) {
        staleRetries++;
        document.getElementById('statusText').textContent = 'Starting... (' + elapsed + 's)';
        setTimeout(poll, 2000);
        return;
      }
      document.getElementById('spinner').style.display = 'none';
      document.getElementById('actions').style.display = 'flex';
      document.getElementById('btnGoLive').style.display = 'none';
      document.getElementById('statusText').className = 'status-text stopped';
      document.getElementById('statusText').textContent = 'Preview stopped';
      return;
    }
    staleRetries = 0;
    let status = d.status || 'running';
    document.getElementById('statusText').textContent = status.charAt(0).toUpperCase() + status.slice(1) + '... (' + elapsed + 's)';
    document.getElementById('spinner').style.display = 'none';
    document.getElementById('actions').style.display = 'flex';
    document.getElementById('btnGoLive').style.display = '';
    const img = document.getElementById('previewImage');
    img.src = '/preview_frame?' + Date.now();
    img.className = 'preview-image';
    img.onerror = function() { this.style.display = 'none'; };
    img.onload = function() { this.style.display = 'block'; };
    setTimeout(poll, 5000);
  } catch(e) {
    if (elapsed < 20) {
      document.getElementById('statusText').textContent = 'Waiting for workflow... (' + elapsed + 's)';
      setTimeout(poll, 2000);
      return;
    }
    document.getElementById('statusText').textContent = 'Connection error, retrying...';
    setTimeout(poll, 5000);
  }
}
const startTime = Date.now();

async function goLive() {
  if (goLiveClicked) return;
  goLiveClicked = true;
  document.getElementById('btnGoLive').disabled = true;
  document.getElementById('btnGoLive').textContent = 'Starting...';
  document.getElementById('statusText').textContent = 'Stopping preview and starting live stream...';
  document.getElementById('spinner').style.display = 'block';
  try {
    const r = await fetch('/preview/go_live');
    const d = await r.json();
    if (d.ok) {
      document.getElementById('statusText').className = 'status-text running';
      document.getElementById('statusText').textContent = 'Live stream started!';
      document.getElementById('spinner').style.display = 'none';
      setTimeout(() => { location.href = '/'; }, 2000);
    } else {
      alert('Error: ' + d.error);
      document.getElementById('btnGoLive').disabled = false;
      document.getElementById('btnGoLive').textContent = '▶ Go Live';
      goLiveClicked = false;
    }
  } catch(e) {
    alert('Connection error');
    document.getElementById('btnGoLive').disabled = false;
    document.getElementById('btnGoLive').textContent = '▶ Go Live';
    goLiveClicked = false;
  }
}

poll();
</script>
</body>
</html>'''

@app.route('/fma_parse', methods=['POST'])
def fma_parse():
    data = request.get_json(force=True)
    url = data.get('url', '').strip()
    if not url or 'freemusicarchive.org' not in url:
        return jsonify({'ok': False, 'error': 'Not a valid FMA URL'})
    try:
        r = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
        if r.status_code != 200:
            return jsonify({'ok': False, 'error': f'HTTP {r.status_code}'})
        import re
        urls = re.findall(r'"fileUrl":"(https://files\.freemusicarchive\.org[^"]+)"', r.text)
        if not urls:
            return jsonify({'ok': False, 'error': 'No tracks found on that page'})
        return jsonify({'ok': True, 'tracks': urls, 'count': len(urls)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@app.route('/tiktok/push_key', methods=['POST'])
def tt_push_key():
    data = request.get_json(force=True)
    key = data.get('key', '').strip()
    if not key:
        return jsonify({'ok': False, 'error': 'No key provided'})
    cfg = load_config()
    cfg['tt_key'] = key
    save_config(cfg)
    log(f'TikTok key pushed via script')
    return jsonify({'ok': True})

HTML_PANEL = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Stream Panel</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',sans-serif;background:#0d1117;color:#c9d1d9}
.container{max-width:900px;margin:0 auto;padding:20px}
h1{font-size:22px;margin-bottom:20px;color:#fff}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:20px;margin-bottom:16px}
.card h2{font-size:16px;margin-bottom:12px;color:#f0f6fc}
.form-group{margin-bottom:12px}
.form-group label{display:block;font-size:13px;color:#8b949e;margin-bottom:4px}
.form-group input,.form-group textarea,.form-group select{width:100%;padding:8px 12px;background:#0d1117;border:1px solid #30363d;border-radius:6px;color:#c9d1d9;font-size:14px}
.form-group input:focus,.form-group select:focus,.form-group textarea:focus{outline:none;border-color:#58a6ff}
.form-group textarea{resize:vertical;min-height:60px}
.btn{display:inline-flex;align-items:center;gap:8px;padding:10px 24px;border:none;border-radius:6px;font-size:15px;font-weight:600;cursor:pointer}
.btn:disabled{opacity:.5;cursor:not-allowed}
.btn-green{background:#238636;color:#fff}
.btn-green:hover:not(:disabled){background:#2ea043}
.btn-red{background:#da3633;color:#fff}
.btn-red:hover:not(:disabled){background:#f85149}
.btn-blue{background:#1f6feb;color:#fff}
.btn-blue:hover:not(:disabled){background:#388bfd}
.btn-grey{background:#21262d;color:#c9d1d9;border:1px solid #30363d}
.btn-grey:hover:not(:disabled){background:#30363d}
.btn-purple{background:#7c3aed;color:#fff}
.btn-purple:hover:not(:disabled){background:#8b5cf6}
.btn-orange{background:#d29922;color:#fff}
.btn-orange:hover:not(:disabled){background:#e3b341}
.btn-sm{padding:6px 14px;font-size:13px}
.actions{display:flex;gap:12px;margin:12px 0;flex-wrap:wrap}
.status-bar{display:flex;align-items:center;gap:16px;padding:12px 16px;background:#0d1117;border:1px solid #30363d;border-radius:6px;margin-bottom:16px}
.status-dot{width:10px;height:10px;border-radius:50%;display:inline-block;margin-right:6px}
.status-dot.live{background:#3fb950;box-shadow:0 0 8px #3fb950}
.status-dot.stopped{background:#f85149}
.log-box{background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:12px;height:300px;overflow-y:auto;font-family:monospace;font-size:12px;line-height:1.5;white-space:pre-wrap}
.log-box .info{color:#8b949e}
.log-box .err{color:#f85149}
.log-box .ok{color:#3fb950}
</style>
</head>
<body>
<div class="container">
<div style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap">
  <a href="/" style="padding:8px 16px;background:#238636;color:#fff;border-radius:6px;text-decoration:none;font-size:14px;font-weight:600">Kick</a>
  <a href="/yt" style="padding:8px 16px;background:#30363d;color:#c9d1d9;border-radius:6px;text-decoration:none;font-size:14px">YouTube</a>
  <a href="/twitch" style="padding:8px 16px;background:#30363d;color:#c9d1d9;border-radius:6px;text-decoration:none;font-size:14px">Twitch</a>
  <a href="/tiktok" style="padding:8px 16px;background:#30363d;color:#c9d1d9;border-radius:6px;text-decoration:none;font-size:14px">TikTok</a>
  <a href="/facebook" style="padding:8px 16px;background:#30363d;color:#c9d1d9;border-radius:6px;text-decoration:none;font-size:14px">Facebook</a>
  <a href="/fb-now" style="padding:8px 16px;background:#30363d;color:#c9d1d9;border-radius:6px;text-decoration:none;font-size:14px">FB-Now</a>
  <a href="/chat" style="padding:8px 16px;background:#30363d;color:#c9d1d9;border-radius:6px;text-decoration:none;font-size:14px">Chat</a>
</div>
<h1>📡 Stream Panel</h1>
<div class="status-bar">
  <span><span class="status-dot" id="statusDot"></span><span class="status-text" id="statusText">Checking...</span></span>
</div>
<div class="card">
  <h2>GitHub Config</h2>
  <div class="form-group">
    <label>GitHub Token (PAT with actions:write)</label>
    <input type="password" name="github_token" id="github_token" placeholder="ghp_...">
  </div>
  <div class="form-row" style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
    <div class="form-group">
      <label>Owner</label>
      <input name="github_owner" id="github_owner" placeholder="your-username">
    </div>
    <div class="form-group">
      <label>Repo</label>
      <input name="github_repo" id="github_repo" placeholder="repo-name">
    </div>
  </div>
</div>
<div class="card">
  <h2>Stream Config</h2>
  <div class="form-group">
    <label>Source URL</label>
    <input type="url" name="source_url" id="source_url" placeholder="YouTube, Twitch, Kick URL (any live stream)">
  </div>
  <div class="form-group">
    <label>Stream Title</label>
    <input type="text" name="stream_title" id="stream_title" placeholder="My Stream Title">
  </div>
  <div class="form-group">
    <label>Stream Description</label>
    <textarea name="stream_description" id="stream_description" rows="2" placeholder="Stream description..."></textarea>
  </div>
  <div class="form-group">
    <label>Output URL (Kick RTMP/SRT)</label>
    <input type="text" name="output_url" id="output_url" placeholder="rtmp://... or srt://...">
  </div>
    <div class="form-group">
      <label>Overlay Text (displayed on stream)</label>
      <div style="display:flex;gap:8px">
        <input type="text" name="overlay_text" id="overlay_text" placeholder="Live Now!" style="flex:1">
        <button class="btn btn-grey btn-sm" onclick="pushOverlay()" style="white-space:nowrap">Push Overlay</button>
      </div>
    </div>
    <div class="form-group">
      <label>Browser Overlay URL (Fusion Chat, alerts, counters, etc.)</label>
      <input type="url" name="browser_overlay_url" id="browser_overlay_url" placeholder="https://kicktools.app/fusion_chat/fusion-chat.html?kick=...">
      <div style="font-size:11px;color:#8b949e;margin-top:2px">Generate one at <a href="/chat" style="color:#58a6ff">Chat Overlay Generator</a> or paste any widget URL</div>
    </div>
    <div class="form-group" style="margin-top:4px">
      <label style="display:flex;align-items:center;gap:8px">
        <input type="checkbox" name="keepalive" id="keepalive" onchange="saveConfig()" style="width:auto">
        Keep Alive (auto-restart after 6h)
      </label>
    </div>
    <div class="actions">
      <button class="btn btn-green" id="btnGoLive" onclick="goLive()">▶ Go Live (Kick)</button>
      <button class="btn btn-red" id="btnStop" onclick="stopStream()" disabled>⏹ Stop</button>
      <button class="btn btn-blue btn-sm" onclick="saveConfig()">💾 Save</button>
      <button class="btn btn-orange btn-sm" onclick="location.href='/preview'">👁 Preview</button>
      <button class="btn btn-grey btn-sm" onclick="testSource()">🔍 Test Source</button>
      <button class="btn btn-grey btn-sm" onclick="document.getElementById('envInput').click()">📄 Upload .env</button>
      <input type="file" id="envInput" accept=".env" style="display:none" onchange="uploadEnv(this.files[0])">
    </div>
    <div id="testResult" style="font-size:12px;color:#8b949e;margin-top:8px"></div>
</div>
<div class="card" style="border-color:#6441a5">
  <h2>Twitch via Restream</h2>
  <div class="form-group">
    <label>Restream RTMP URL</label>
    <input type="text" name="twt_restream_url" id="twt_restream_url" placeholder="rtmp://live.restream.io/live/restream_token_XXXX">
    <div style="font-size:11px;color:#8b949e;margin-top:2px">
      Get from <a href="https://restream.io/streaming" target="_blank" style="color:#58a6ff">restream.io/streaming</a> — add Twitch as a channel. Paste full RTMP URL.
    </div>
  </div>
  <div class="form-group">
    <label>Twitch Repo</label>
    <input name="twt_repo" id="twt_repo" placeholder="8dca7ff25e47b8cc0e104b9f-twt">
  </div>
  <div class="form-group">
    <label>YouTube Cookies (for YouTube sources — export from Chrome via "Get cookies.txt")</label>
    <textarea name="yt_cookies" id="yt_cookies" rows="3" placeholder="Paste Netscape cookies.txt content from Chrome (YouTube must be logged in)"></textarea>
    <div style="font-size:11px;color:#8b949e;margin-top:2px">
      Use <a href="https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc" target="_blank" style="color:#58a6ff">Get cookies.txt LOCALLY</a> extension on youtube.com. Shared across YT/FB-Now/TikTok/Twitch panels.
    </div>
  </div>
  <div class="actions">
    <button class="btn btn-purple" id="btnGoLiveTWT" onclick="goLiveTWT()">▶ Go Live (Twitch)</button>
    <button class="btn btn-red" id="btnStopTWT" onclick="stopTWT()" disabled>⏹ Stop Twitch</button>
  </div>
</div>
<div class="card">
  <h2>Logs</h2>
  <div class="log-box" id="logBox">Waiting...</div>
</div>
</div>
<script>
function applyForm(c) {
  if (!c) return;
  for (const [k,v] of Object.entries(c)) {
    const el = document.getElementById(k);
    if (el) el.value = v;
  }
}
function readForm() {
  const d = {};
  document.querySelectorAll('input,textarea,select').forEach(el => {
    if (el.type === 'checkbox') d[el.name] = el.checked;
    else if (el.name) d[el.name] = el.value;
  });
  return d;
}
function saveConfig(cb) {
  fetch('/config', {method:'POST', body:JSON.stringify(readForm()), headers:{'Content-Type':'application/json'}})
    .then(r=>r.json()).then(d=>{ addLog('Config saved','ok'); if(cb) cb(); })
    .catch(e=>{ addLog('Save failed','err'); if(cb) cb(); });
}
function testSource() {
  const el = document.getElementById('testResult');
  el.textContent = 'Checking...';
  fetch('/resolve').then(r=>r.json()).then(d=>{
    el.textContent = d.ok ? '✓ Live — HLS resolved' : '✗ Not live';
  }).catch(()=>el.textContent='✗ Failed');
}
function uploadEnv(file) {
  if (!file) return;
  const fd = new FormData();
  fd.append('env_file', file);
  addLog('Uploading .env...','info');
  fetch('/upload_env', {method:'POST', body:fd})
    .then(r=>r.json()).then(d=>{
      addLog(d.ok ? '.env uploaded successfully' : 'Error: '+d.error, d.ok?'ok':'err');
      if(d.ok) setTimeout(()=>location.reload(), 1500);
    }).catch(e=>addLog('Upload failed','err'));
}
function goLive() {
  const btn = document.getElementById('btnGoLive');
  if (btn.dataset.running === 'true') return;
  btn.dataset.running = 'true';
  btn.disabled = true;
  addLog('Starting all outputs...','info');
  saveConfig(() => {
    fetch('/start').then(r=>r.json()).then(d=>{
      if(!d.ok) addLog('Error: '+d.error,'err');
      btn.dataset.running = 'false';
      btn.disabled = false;
    }).catch(e=>{ addLog('Start failed','err'); }).finally(()=>{ btn.dataset.running = 'false'; btn.disabled = false; });
  });
}

function stopStream() {
  document.getElementById('btnStop').disabled = true;
  addLog('Stopping...','warn');
  fetch('/stop').then(r=>r.json()).then(d=>{
    addLog(d.ok ? 'Stopped' : 'Error: '+d.error, d.ok ? 'warn' : 'err');
  }).catch(e=>addLog('Stop failed','err'));
}
function goLiveTWT() {
  document.getElementById('btnGoLiveTWT').disabled = true;
  addLog('Starting Twitch via Restream...','info');
  saveConfig(() => {
    fetch('/twitch/start').then(r=>r.json()).then(d=>{
      if(!d.ok) { addLog('Error: '+d.error,'err'); }
      document.getElementById('btnGoLiveTWT').disabled = false;
    }).catch(e=>{ addLog('Twitch start failed','err'); document.getElementById('btnGoLiveTWT').disabled = false; });
  });
}
function stopTWT() {
  document.getElementById('btnStopTWT').disabled = true;
  addLog('Stopping Twitch...','warn');
  fetch('/twitch/stop').then(r=>r.json()).then(d=>{
    addLog(d.ok ? 'Twitch stopped' : 'Error: '+d.error, d.ok ? 'warn' : 'err');
  }).catch(e=>addLog('Twitch stop failed','err'));
}
function pushOverlay() {
  saveConfig(() => addLog('Overlay pushed','ok'));
}
function addLog(msg,cls='info') {
  const box = document.getElementById('logBox');
  box.innerHTML += '<span class="'+cls+'">['+new Date().toLocaleTimeString()+'] '+msg+'</span>\n';
  box.scrollTop = box.scrollHeight;
}
function fetchFMAtracks() {
  const url = document.getElementById('fmaUrl').value.trim();
  if (!url) { addLog('Enter an FMA album URL first','err'); return; }
  addLog('Fetching tracks from FMA...','info');
  fetch('/fma_parse', {method:'POST', body:JSON.stringify({url}), headers:{'Content-Type':'application/json'}})
    .then(r=>r.json()).then(d=>{
      if (!d.ok) { addLog('Error: '+d.error,'err'); return; }
      addLog('Loaded '+d.count+' tracks from FMA','ok');
    }).catch(e=>addLog('Fetch failed','err'));
}
function updateStatus() {
  fetch('/status').then(r=>r.json()).then(d=>{
    const dot = document.getElementById('statusDot');
    const txt = document.getElementById('statusText');
    if(d.live) {
      dot.className = 'status-dot live';
      txt.textContent = '● LIVE' + (d.keepalive ? ' (auto-restart)' : '');
      document.getElementById('btnGoLive').disabled = true;
      document.getElementById('btnStop').disabled = false;
    } else {
      dot.className = 'status-dot stopped';
      txt.textContent = '○ Stopped';
      document.getElementById('btnGoLive').disabled = false;
      document.getElementById('btnStop').disabled = true;
    }
    if(d.config) document.getElementById('keepalive').checked = d.config.keepalive;
  }).catch(()=>{});
}
function fetchLogs() {
  fetch('/logs').then(r=>r.text()).then(t=>{
    const box = document.getElementById('logBox');
    if(t) box.innerHTML = t;
    box.scrollTop = box.scrollHeight;
  }).catch(()=>{});
}
fetch('/status').then(r=>r.json()).then(d=>{ if(d.config) applyForm(d.config); });
setInterval(updateStatus, 3000);
setInterval(fetchLogs, 2000);
</script>
</body>
</html>'''

HTML_TWT_PANEL = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Twitch Stream Panel</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',sans-serif;background:#0d1117;color:#c9d1d9}
.container{max-width:900px;margin:0 auto;padding:20px}
h1{font-size:22px;margin-bottom:20px;color:#fff}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:20px;margin-bottom:16px}
.card h2{font-size:16px;margin-bottom:12px;color:#f0f6fc}
.form-group{margin-bottom:12px}
.form-group label{display:block;font-size:13px;color:#8b949e;margin-bottom:4px}
.form-group input,.form-group textarea,.form-group select{width:100%;padding:8px 12px;background:#0d1117;border:1px solid #30363d;border-radius:6px;color:#c9d1d9;font-size:14px}
.form-group input:focus,.form-group select:focus,.form-group textarea:focus{outline:none;border-color:#58a6ff}
.form-group textarea{resize:vertical;min-height:60px}
.btn{display:inline-flex;align-items:center;gap:8px;padding:10px 24px;border:none;border-radius:6px;font-size:15px;font-weight:600;cursor:pointer}
.btn:disabled{opacity:.5;cursor:not-allowed}
.btn-green{background:#238636;color:#fff}
.btn-green:hover:not(:disabled){background:#2ea043}
.btn-purple{background:#7c3aed;color:#fff}
.btn-purple:hover:not(:disabled){background:#8b5cf6}
.btn-red{background:#da3633;color:#fff}
.btn-red:hover:not(:disabled){background:#f85149}
.btn-blue{background:#1f6feb;color:#fff}
.btn-blue:hover:not(:disabled){background:#388bfd}
.btn-grey{background:#21262d;color:#c9d1d9;border:1px solid #30363d}
.btn-grey:hover:not(:disabled){background:#30363d}
.btn-orange{background:#d29922;color:#fff}
.btn-orange:hover:not(:disabled){background:#e3b341}
.btn-sm{padding:6px 14px;font-size:13px}
.actions{display:flex;gap:12px;margin:12px 0;flex-wrap:wrap}
.status-bar{display:flex;align-items:center;gap:16px;padding:12px 16px;background:#0d1117;border:1px solid #30363d;border-radius:6px;margin-bottom:16px}
.status-dot{width:10px;height:10px;border-radius:50%;display:inline-block;margin-right:6px}
.status-dot.live{background:#3fb950;box-shadow:0 0 8px #3fb950}
.status-dot.stopped{background:#f85149}
.log-box{background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:12px;height:300px;overflow-y:auto;font-family:monospace;font-size:12px;line-height:1.5;white-space:pre-wrap}
.log-box .info{color:#8b949e}
.log-box .err{color:#f85149}
.log-box .ok{color:#3fb950}
</style>
</head>
<body>
<div class="container">
<div style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap">
  <a href="/" style="padding:8px 16px;background:#30363d;color:#c9d1d9;border-radius:6px;text-decoration:none;font-size:14px">Kick</a>
  <a href="/yt" style="padding:8px 16px;background:#30363d;color:#c9d1d9;border-radius:6px;text-decoration:none;font-size:14px">YouTube</a>
  <a href="/twitch" style="padding:8px 16px;background:#7c3aed;color:#fff;border-radius:6px;text-decoration:none;font-size:14px;font-weight:600">Twitch</a>
  <a href="/tiktok" style="padding:8px 16px;background:#30363d;color:#c9d1d9;border-radius:6px;text-decoration:none;font-size:14px">TikTok</a>
  <a href="/facebook" style="padding:8px 16px;background:#30363d;color:#c9d1d9;border-radius:6px;text-decoration:none;font-size:14px">Facebook</a>
  <a href="/fb-now" style="padding:8px 16px;background:#30363d;color:#c9d1d9;border-radius:6px;text-decoration:none;font-size:14px">FB-Now</a>
  <a href="/chat" style="padding:8px 16px;background:#30363d;color:#c9d1d9;border-radius:6px;text-decoration:none;font-size:14px">Chat</a>
</div>
<h1>Twitch Stream Panel</h1>
<div class="status-bar">
  <span><span class="status-dot" id="statusDot"></span><span class="status-text" id="statusText">Checking...</span></span>
</div>
<div class="card">
  <h2>GitHub Config</h2>
  <div class="form-group">
    <label>GitHub Token</label>
    <input type="password" name="github_token" id="github_token" placeholder="ghp_...">
  </div>
  <div class="form-row" style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
    <div class="form-group">
      <label>Owner</label>
      <input name="github_owner" id="github_owner" placeholder="your-username">
    </div>
    <div class="form-group">
      <label>Twitch Repo</label>
      <input name="twt_repo" id="twt_repo" placeholder="8dca7ff25e47b8cc0e104b9f-twt">
    </div>
  </div>
</div>
<div class="card">
  <h2>Stream Config</h2>
    <div class="form-group">
      <label>Source URL (Twitch or YouTube)</label>
      <input type="url" name="twt_url" id="twt_url" placeholder="https://www.twitch.tv/streamer or https://youtube.com/watch?v=...">
    </div>
  <div class="form-group">
    <label>Twitch Client ID</label>
    <input type="text" name="twt_client_id" id="twt_client_id" placeholder="Your Twitch app client ID">
  </div>
  <div class="form-group">
    <label>Twitch OAuth Token (scope: channel:read:stream_key)</label>
    <div style="display:flex;gap:8px">
      <input type="password" name="twt_token" id="twt_token" placeholder="oauth:... or ghp_..." style="flex:1">
      <button class="btn btn-grey btn-sm" onclick="fetchTwitchKey()" style="white-space:nowrap">🔑 Fetch Key</button>
    </div>
  </div>
  <div class="form-group">
    <label>Twitch Stream Key</label>
    <input type="text" name="twt_key" id="twt_key" placeholder="live_xxxxxxxxx_xxxxxxxxxxxxxxxxxx">
  </div>
  <div class="form-group">
    <label>Restream RTMP URL (for TikTok/Twitch relay via Restream)</label>
    <input type="text" name="twt_restream_url" id="twt_restream_url" placeholder="rtmp://live.restream.io/live/restream_token_XXXX">
    <div style="font-size:11px;color:#8b949e;margin-top:2px">
      Get from <a href="https://restream.io/streaming" target="_blank" style="color:#58a6ff">restream.io/streaming</a> — add Twitch as a channel. Paste full RTMP URL. If set, this is used instead of Twitch Stream Key.
    </div>
  </div>
    <div class="form-group">
      <label>Overlay Text (displayed on stream)</label>
      <div style="display:flex;gap:8px">
        <input type="text" name="overlay_text" id="overlay_text" placeholder="Live on Twitch!" style="flex:1">
        <button class="btn btn-grey btn-sm" onclick="pushOverlay()" style="white-space:nowrap">Push Overlay</button>
      </div>
    </div>
    <div class="form-group">
      <label>Browser Overlay URL (Fusion Chat, alerts, counters, etc.)</label>
      <input type="url" name="browser_overlay_url" id="browser_overlay_url" placeholder="https://kicktools.app/fusion_chat/fusion-chat.html?kick=...">
      <div style="font-size:11px;color:#8b949e;margin-top:2px">Generate one at <a href="/chat" style="color:#58a6ff">Chat Overlay Generator</a> or paste any widget URL</div>
    </div>
    <div class="form-group">
      <label>YouTube Cookies (base64-encoded cookies.txt for YouTube sources)</label>
      <textarea name="cookies_b64" id="cookies_b64" rows="2" placeholder="Paste base64-encoded cookies.txt here..."></textarea>
      <div style="font-size:11px;color:#8b949e;margin-top:2px">For YouTube sources: <code>base64 -w0 cookies.txt</code></div>
    </div>
    <div class="form-group" style="margin-top:4px">
      <label style="display:flex;align-items:center;gap:8px">
        <input type="checkbox" name="twt_keepalive" id="twt_keepalive" onchange="saveConfig()" style="width:auto">
        Keep Alive (auto-restart after 6h)
      </label>
    </div>
    <div class="actions">
      <button class="btn btn-purple" id="btnGoLive" onclick="goLive()">▶ Go Live (Twitch)</button>
      <button class="btn btn-red" id="btnStop" onclick="stopStream()" disabled>⏹ Stop</button>
      <button class="btn btn-blue btn-sm" onclick="saveConfig()">💾 Save</button>
      <button class="btn btn-orange btn-sm" onclick="location.href='/preview'">👁 Preview</button>
      <button class="btn btn-grey btn-sm" onclick="testSource()">🔍 Test Source</button>
      <button class="btn btn-grey btn-sm" onclick="document.getElementById('envInput').click()">📄 Upload .env</button>
      <input type="file" id="envInput" accept=".env" style="display:none" onchange="uploadEnv(this.files[0])">
    </div>
    <div id="testResult" style="font-size:12px;color:#8b949e;margin-top:8px"></div>
</div>
<div class="card">
  <h2>Logs</h2>
  <div class="log-box" id="logBox">Waiting...</div>
</div>
</div>
<script>
function applyForm(c) {
  if (!c) return;
  for (const [k,v] of Object.entries(c)) {
    const el = document.getElementById(k);
    if (el) el.value = v;
  }
}
function readForm() {
  const d = {};
  document.querySelectorAll('input,textarea,select').forEach(el => {
    if (el.type === 'checkbox') d[el.name] = el.checked;
    else if (el.name) d[el.name] = el.value;
  });
  return d;
}
function saveConfig(cb) {
  fetch('/config', {method:'POST', body:JSON.stringify(readForm()), headers:{'Content-Type':'application/json'}})
    .then(r=>r.json()).then(d=>{ addLog('Config saved','ok'); if(cb) cb(); })
    .catch(e=>{ addLog('Save failed','err'); if(cb) cb(); });
}
function testSource() {
  const el = document.getElementById('testResult');
  el.textContent = 'Checking...';
  fetch('/twitch/resolve').then(r=>r.json()).then(d=>{
    el.textContent = d.ok ? '✓ Live — HLS resolved' : '✗ Not live';
  }).catch(()=>el.textContent='✗ Failed');
}
function fetchTwitchKey() {
  addLog('Fetching Twitch stream key...','info');
  saveConfig(() => {
    fetch('/twitch/fetch_key').then(r=>r.json()).then(d=>{
      if(d.ok) {
        document.getElementById('twt_key').value = d.key;
        addLog('Stream key fetched and saved','ok');
      } else {
        addLog('Error: '+d.error,'err');
      }
    }).catch(e=>addLog('Fetch failed','err'));
  });
}
function uploadEnv(file) {
  if (!file) return;
  const fd = new FormData();
  fd.append('env_file', file);
  addLog('Uploading .env...','info');
  fetch('/upload_env', {method:'POST', body:fd})
    .then(r=>r.json()).then(d=>{
      addLog(d.ok ? '.env uploaded successfully' : 'Error: '+d.error, d.ok?'ok':'err');
      if(d.ok) setTimeout(()=>location.reload(), 1500);
    }).catch(e=>addLog('Upload failed','err'));
}
function goLive() {
  document.getElementById('btnGoLive').disabled = true;
  addLog('Starting Twitch stream...','info');
  saveConfig(() => {
    fetch('/twitch/start').then(r=>r.json()).then(d=>{
      if(!d.ok) { addLog('Error: '+d.error,'err'); document.getElementById('btnGoLive').disabled = false; }
    }).catch(e=>{ addLog('Start failed','err'); document.getElementById('btnGoLive').disabled = false; });
  });
}
function stopStream() {
  document.getElementById('btnStop').disabled = true;
  addLog('Stopping...','warn');
  fetch('/twitch/stop').then(r=>r.json()).then(d=>{
    addLog(d.ok ? 'Stopped' : 'Error: '+d.error, d.ok ? 'warn' : 'err');
  }).catch(e=>addLog('Stop failed','err'));
}
function pushOverlay() {
  saveConfig(() => addLog('Overlay pushed','ok'));
}
function fetchFMAtracks() {
  const url = document.getElementById('fmaUrl').value.trim();
  if (!url) { addLog('Enter an FMA album URL first','err'); return; }
  addLog('Fetching tracks from FMA...','info');
  fetch('/fma_parse', {method:'POST', body:JSON.stringify({url}), headers:{'Content-Type':'application/json'}})
    .then(r=>r.json()).then(d=>{
      if (!d.ok) { addLog('Error: '+d.error,'err'); return; }
      addLog('Loaded '+d.count+' tracks from FMA','ok');
      saveConfig();
    }).catch(e=>addLog('Fetch failed','err'));
}
function addLog(msg,cls='info') {
  const box = document.getElementById('logBox');
  box.innerHTML += '<span class="'+cls+'">['+new Date().toLocaleTimeString()+'] '+msg+'</span>\n';
  box.scrollTop = box.scrollHeight;
}
function updateStatus() {
  fetch('/twitch/status').then(r=>r.json()).then(d=>{
    const dot = document.getElementById('statusDot');
    const txt = document.getElementById('statusText');
    if(d.live) {
      dot.className = 'status-dot live';
      txt.textContent = '● LIVE' + (d.keepalive ? ' (auto-restart)' : '');
      document.getElementById('btnGoLive').disabled = true;
      document.getElementById('btnStop').disabled = false;
    } else {
      dot.className = 'status-dot stopped';
      txt.textContent = '○ Stopped';
      document.getElementById('btnGoLive').disabled = false;
      document.getElementById('btnStop').disabled = true;
    }
    if(d.config) document.getElementById('twt_keepalive').checked = d.config.twt_keepalive;
  }).catch(()=>{});
}
function fetchLogs() {
  fetch('/logs').then(r=>r.text()).then(t=>{
    const box = document.getElementById('logBox');
    if(t) box.innerHTML = t;
    box.scrollTop = box.scrollHeight;
  }).catch(()=>{});
}
fetch('/twitch/status').then(r=>r.json()).then(d=>{ if(d.config) applyForm(d.config); });
setInterval(updateStatus, 3000);
setInterval(fetchLogs, 2000);
</script>
</body>
</html>'''

HTML_YT_PANEL = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>YouTube Stream Panel</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',sans-serif;background:#0d1117;color:#c9d1d9}
.container{max-width:900px;margin:0 auto;padding:20px}
h1{font-size:22px;margin-bottom:20px;color:#fff}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:20px;margin-bottom:16px}
.card h2{font-size:16px;margin-bottom:12px;color:#f0f6fc}
.form-group{margin-bottom:12px}
.form-group label{display:block;font-size:13px;color:#8b949e;margin-bottom:4px}
.form-group input,.form-group textarea,.form-group select{width:100%;padding:8px 12px;background:#0d1117;border:1px solid #30363d;border-radius:6px;color:#c9d1d9;font-size:14px}
.form-group input:focus,.form-group select:focus,.form-group textarea:focus{outline:none;border-color:#58a6ff}
.form-group textarea{resize:vertical;min-height:60px}
.btn{display:inline-flex;align-items:center;gap:8px;padding:10px 24px;border:none;border-radius:6px;font-size:15px;font-weight:600;cursor:pointer}
.btn:disabled{opacity:.5;cursor:not-allowed}
.btn-green{background:#238636;color:#fff}
.btn-green:hover:not(:disabled){background:#2ea043}
.btn-red{background:#da3633;color:#fff}
.btn-red:hover:not(:disabled){background:#f85149}
.btn-blue{background:#1f6feb;color:#fff}
.btn-blue:hover:not(:disabled){background:#388bfd}
.btn-grey{background:#21262d;color:#c9d1d9;border:1px solid #30363d}
.btn-grey:hover:not(:disabled){background:#30363d}
.btn-orange{background:#d29922;color:#fff}
.btn-orange:hover:not(:disabled){background:#e3b341}
.btn-sm{padding:6px 14px;font-size:13px}
.actions{display:flex;gap:12px;margin:12px 0;flex-wrap:wrap}
.status-bar{display:flex;align-items:center;gap:16px;padding:12px 16px;background:#0d1117;border:1px solid #30363d;border-radius:6px;margin-bottom:16px}
.status-dot{width:10px;height:10px;border-radius:50%;display:inline-block;margin-right:6px}
.status-dot.live{background:#3fb950;box-shadow:0 0 8px #3fb950}
.status-dot.stopped{background:#f85149}
.log-box{background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:12px;height:300px;overflow-y:auto;font-family:monospace;font-size:12px;line-height:1.5;white-space:pre-wrap}
.log-box .info{color:#8b949e}
.log-box .err{color:#f85149}
.log-box .ok{color:#3fb950}
</style>
</head>
<body>
<div class="container">
<div style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap">
  <a href="/" style="padding:8px 16px;background:#30363d;color:#c9d1d9;border-radius:6px;text-decoration:none;font-size:14px">Kick</a>
  <a href="/yt" style="padding:8px 16px;background:#ff0000;color:#fff;border-radius:6px;text-decoration:none;font-size:14px;font-weight:600">YouTube</a>
  <a href="/twitch" style="padding:8px 16px;background:#30363d;color:#c9d1d9;border-radius:6px;text-decoration:none;font-size:14px">Twitch</a>
  <a href="/tiktok" style="padding:8px 16px;background:#30363d;color:#c9d1d9;border-radius:6px;text-decoration:none;font-size:14px">TikTok</a>
  <a href="/facebook" style="padding:8px 16px;background:#30363d;color:#c9d1d9;border-radius:6px;text-decoration:none;font-size:14px">Facebook</a>
  <a href="/fb-now" style="padding:8px 16px;background:#30363d;color:#c9d1d9;border-radius:6px;text-decoration:none;font-size:14px">FB-Now</a>
  <a href="/chat" style="padding:8px 16px;background:#30363d;color:#c9d1d9;border-radius:6px;text-decoration:none;font-size:14px">Chat</a>
</div>
<h1>YouTube Stream Panel</h1>
<div class="status-bar">
  <span><span class="status-dot" id="statusDot"></span><span class="status-text" id="statusText">Checking...</span></span>
</div>
<div class="card">
  <h2>GitHub Config</h2>
  <div class="form-group">
    <label>GitHub Token</label>
    <input type="password" name="github_token" id="github_token" placeholder="ghp_...">
  </div>
  <div class="form-row" style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
    <div class="form-group">
      <label>Owner</label>
      <input name="github_owner" id="github_owner" placeholder="your-username">
    </div>
    <div class="form-group">
      <label>YT Repo</label>
      <input name="yt_repo" id="yt_repo" placeholder="8dca7ff25e47b8cc0e104b9f-yt">
    </div>
  </div>
</div>
<div class="card">
  <h2>Stream Config</h2>
  <div class="form-group">
    <label>Source URL (Twitch)</label>
    <input type="url" name="yt_url" id="yt_url" placeholder="https://www.twitch.tv/streamer">
  </div>
  <div class="form-group">
    <label>YouTube Stream Key</label>
    <input type="text" name="yt_key" id="yt_key" placeholder="xxxx-xxxx-xxxx-xxxx">
  </div>
  <div class="form-group">
    <label>YouTube Cookies (paste Netscape cookies.txt content)</label>
    <textarea name="yt_cookies" id="yt_cookies" rows="4" placeholder="Paste cookies.txt content here (export from browser using Get cookies.txt extension)" style="font-family:monospace;font-size:11px"></textarea>
  </div>
    <div class="form-group">
      <label>Overlay Text (displayed on stream)</label>
      <div style="display:flex;gap:8px">
        <input type="text" name="overlay_text" id="overlay_text" placeholder="Live on YouTube!" style="flex:1">
        <button class="btn btn-grey btn-sm" onclick="pushOverlay()" style="white-space:nowrap">Push Overlay</button>
      </div>
    </div>
    <div class="form-group" style="margin-top:4px">
      <label style="display:flex;align-items:center;gap:8px">
        <input type="checkbox" name="yt_chat_enabled" id="yt_chat_enabled" onchange="saveConfig()" style="width:auto">
        Enable YouTube Live Chat overlay
      </label>
      <div style="font-size:11px;color:#8b949e;margin-left:20px">Shows live chat messages on screen (needs API key below)</div>
    </div>
    <div class="form-group">
      <label>YouTube Data API v3 Key</label>
      <input type="text" name="youtube_api_key" id="youtube_api_key" placeholder="AIzaSy...">
      <div style="font-size:11px;color:#8b949e;margin-top:2px">Get from <a href="https://console.cloud.google.com/apis/credentials" target="_blank" style="color:#58a6ff">Google Cloud Console</a> (enable YouTube Data API v3)</div>
    </div>
    <div class="form-group">
      <label>Browser Overlay URL (Fusion Chat, alerts, counters, etc.)</label>
      <input type="url" name="browser_overlay_url" id="browser_overlay_url" placeholder="https://kicktools.app/fusion_chat/fusion-chat.html?kick=...">
      <div style="font-size:11px;color:#8b949e;margin-top:2px">Generate one at <a href="/chat" style="color:#58a6ff">Chat Overlay Generator</a> or paste any widget URL</div>
    </div>
    <div class="form-group" style="margin-top:4px">
      <label style="display:flex;align-items:center;gap:8px">
        <input type="checkbox" name="yt_keepalive" id="yt_keepalive" onchange="saveConfig()" style="width:auto">
        Keep Alive (auto-restart after 6h)
      </label>
    </div>
    <div class="actions">
      <button class="btn btn-red" id="btnGoLive" onclick="goLive()" style="background:#ff0000;color:#fff">▶ Go Live (YouTube)</button>
      <button class="btn btn-red" id="btnStop" onclick="stopStream()" disabled>⏹ Stop</button>
      <button class="btn btn-blue btn-sm" onclick="saveConfig()">💾 Save</button>
      <button class="btn btn-orange btn-sm" onclick="location.href='/preview'">👁 Preview</button>
      <button class="btn btn-grey btn-sm" onclick="testSource()">🔍 Test Source</button>
      <button class="btn btn-grey btn-sm" onclick="document.getElementById('envInput').click()">📄 Upload .env</button>
      <input type="file" id="envInput" accept=".env" style="display:none" onchange="uploadEnv(this.files[0])">
    </div>
    <div id="testResult" style="font-size:12px;color:#8b949e;margin-top:8px"></div>
</div>
<div class="card">
  <h2>Logs</h2>
  <div class="log-box" id="logBox">Waiting...</div>
</div>
</div>
<script>
function applyForm(c) {
  if (!c) return;
  for (const [k,v] of Object.entries(c)) {
    const el = document.getElementById(k);
    if (el) el.value = v;
  }
}
function readForm() {
  const d = {};
  document.querySelectorAll('input,textarea,select').forEach(el => {
    if (el.type === 'checkbox') d[el.name] = el.checked;
    else if (el.name) d[el.name] = el.value;
  });
  return d;
}
function saveConfig(cb) {
  fetch('/config', {method:'POST', body:JSON.stringify(readForm()), headers:{'Content-Type':'application/json'}})
    .then(r=>r.json()).then(d=>{ addLog('Config saved','ok'); if(cb) cb(); })
    .catch(e=>{ addLog('Save failed','err'); if(cb) cb(); });
}
function testSource() {
  const el = document.getElementById('testResult');
  el.textContent = 'Checking...';
  fetch('/yt/resolve').then(r=>r.json()).then(d=>{
    el.textContent = d.ok ? '✓ Live — HLS resolved' : '✗ Not live';
  }).catch(()=>el.textContent='✗ Failed');
}
function uploadEnv(file) {
  if (!file) return;
  const fd = new FormData();
  fd.append('env_file', file);
  addLog('Uploading .env...','info');
  fetch('/upload_env', {method:'POST', body:fd})
    .then(r=>r.json()).then(d=>{
      addLog(d.ok ? '.env uploaded successfully' : 'Error: '+d.error, d.ok?'ok':'err');
      if(d.ok) setTimeout(()=>location.reload(), 1500);
    }).catch(e=>addLog('Upload failed','err'));
}
function goLive() {
  document.getElementById('btnGoLive').disabled = true;
  addLog('Starting YouTube stream...','info');
  saveConfig(() => {
    fetch('/yt/start').then(r=>r.json()).then(d=>{
      if(!d.ok) { addLog('Error: '+d.error,'err'); document.getElementById('btnGoLive').disabled = false; }
    }).catch(e=>{ addLog('Start failed','err'); document.getElementById('btnGoLive').disabled = false; });
  });
}
function stopStream() {
  document.getElementById('btnStop').disabled = true;
  addLog('Stopping...','warn');
  fetch('/yt/stop').then(r=>r.json()).then(d=>{
    addLog(d.ok ? 'Stopped' : 'Error: '+d.error, d.ok ? 'warn' : 'err');
  }).catch(e=>addLog('Stop failed','err'));
}
function pushOverlay() {
  saveConfig(() => addLog('Overlay pushed','ok'));
}
function addLog(msg,cls='info') {
  const box = document.getElementById('logBox');
  box.innerHTML += '<span class="'+cls+'">['+new Date().toLocaleTimeString()+'] '+msg+'</span>\n';
  box.scrollTop = box.scrollHeight;
}
function fetchFMAtracks() {
  const url = document.getElementById('fmaUrl').value.trim();
  if (!url) { addLog('Enter an FMA album URL first','err'); return; }
  addLog('Fetching tracks from FMA...','info');
  fetch('/fma_parse', {method:'POST', body:JSON.stringify({url}), headers:{'Content-Type':'application/json'}})
    .then(r=>r.json()).then(d=>{
      if (!d.ok) { addLog('Error: '+d.error,'err'); return; }
      addLog('Loaded '+d.count+' tracks from FMA','ok');
      saveConfig();
    }).catch(e=>addLog('Fetch failed','err'));
}
function updateStatus() {
  fetch('/yt/status').then(r=>r.json()).then(d=>{
    const dot = document.getElementById('statusDot');
    const txt = document.getElementById('statusText');
    if(d.live) {
      dot.className = 'status-dot live';
      txt.textContent = '● LIVE' + (d.keepalive ? ' (auto-restart)' : '');
      document.getElementById('btnGoLive').disabled = true;
      document.getElementById('btnStop').disabled = false;
    } else {
      dot.className = 'status-dot stopped';
      txt.textContent = '○ Stopped';
      document.getElementById('btnGoLive').disabled = false;
      document.getElementById('btnStop').disabled = true;
    }
    if(d.config) document.getElementById('yt_keepalive').checked = d.config.yt_keepalive;
  }).catch(()=>{});
}
function fetchLogs() {
  fetch('/logs').then(r=>r.text()).then(t=>{
    const box = document.getElementById('logBox');
    if(t) box.innerHTML = t;
    box.scrollTop = box.scrollHeight;
  }).catch(()=>{});
}
fetch('/yt/status').then(r=>r.json()).then(d=>{ if(d.config) applyForm(d.config); });
setInterval(updateStatus, 3000);
setInterval(fetchLogs, 2000);
</script>
</body>
</html>'''

HTML_TT_PANEL = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TikTok Stream Panel</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',sans-serif;background:#0d1117;color:#c9d1d9}
.container{max-width:900px;margin:0 auto;padding:20px}
h1{font-size:22px;margin-bottom:20px;color:#fff}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:20px;margin-bottom:16px}
.card h2{font-size:16px;margin-bottom:12px;color:#f0f6fc}
.form-group{margin-bottom:12px}
.form-group label{display:block;font-size:13px;color:#8b949e;margin-bottom:4px}
.form-group input,.form-group textarea,.form-group select{width:100%;padding:8px 12px;background:#0d1117;border:1px solid #30363d;border-radius:6px;color:#c9d1d9;font-size:14px}
.form-group input:focus,.form-group select:focus,.form-group textarea:focus{outline:none;border-color:#58a6ff}
.form-group textarea{resize:vertical;min-height:60px}
.btn{display:inline-flex;align-items:center;gap:8px;padding:10px 24px;border:none;border-radius:6px;font-size:15px;font-weight:600;cursor:pointer}
.btn:disabled{opacity:.5;cursor:not-allowed}
.btn-green{background:#238636;color:#fff}
.btn-green:hover:not(:disabled){background:#2ea043}
.btn-pink{background:#d43089;color:#fff}
.btn-pink:hover:not(:disabled){background:#e84fa3}
.btn-red{background:#da3633;color:#fff}
.btn-red:hover:not(:disabled){background:#f85149}
.btn-blue{background:#1f6feb;color:#fff}
.btn-blue:hover:not(:disabled){background:#388bfd}
.btn-grey{background:#21262d;color:#c9d1d9;border:1px solid #30363d}
.btn-grey:hover:not(:disabled){background:#30363d}
.btn-orange{background:#d29922;color:#fff}
.btn-orange:hover:not(:disabled){background:#e3b341}
.btn-sm{padding:6px 14px;font-size:13px}
.actions{display:flex;gap:12px;margin:12px 0;flex-wrap:wrap}
.status-bar{display:flex;align-items:center;gap:16px;padding:12px 16px;background:#0d1117;border:1px solid #30363d;border-radius:6px;margin-bottom:16px}
.status-dot{width:10px;height:10px;border-radius:50%;display:inline-block;margin-right:6px}
.status-dot.live{background:#3fb950;box-shadow:0 0 8px #3fb950}
.status-dot.stopped{background:#f85149}
.log-box{background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:12px;height:300px;overflow-y:auto;font-family:monospace;font-size:12px;line-height:1.5;white-space:pre-wrap}
.log-box .info{color:#8b949e}
.log-box .err{color:#f85149}
.log-box .ok{color:#3fb950}
</style>
</head>
<body>
<div class="container">
<div style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap">
  <a href="/" style="padding:8px 16px;background:#30363d;color:#c9d1d9;border-radius:6px;text-decoration:none;font-size:14px">Kick</a>
  <a href="/yt" style="padding:8px 16px;background:#30363d;color:#c9d1d9;border-radius:6px;text-decoration:none;font-size:14px">YouTube</a>
  <a href="/twitch" style="padding:8px 16px;background:#30363d;color:#c9d1d9;border-radius:6px;text-decoration:none;font-size:14px">Twitch</a>
  <a href="/tiktok" style="padding:8px 16px;background:#d43089;color:#fff;border-radius:6px;text-decoration:none;font-size:14px;font-weight:600">TikTok</a>
  <a href="/facebook" style="padding:8px 16px;background:#30363d;color:#c9d1d9;border-radius:6px;text-decoration:none;font-size:14px">Facebook</a>
  <a href="/fb-now" style="padding:8px 16px;background:#30363d;color:#c9d1d9;border-radius:6px;text-decoration:none;font-size:14px">FB-Now</a>
  <a href="/chat" style="padding:8px 16px;background:#30363d;color:#c9d1d9;border-radius:6px;text-decoration:none;font-size:14px">Chat</a>
</div>
<h1>TikTok Stream Panel <span style="font-size:13px;color:#8b949e;font-weight:normal">(via Restream)</span></h1>
<div class="status-bar">
  <span><span class="status-dot" id="statusDot"></span><span class="status-text" id="statusText">Checking...</span></span>
</div>
<div class="card">
  <h2>GitHub Config</h2>
  <div class="form-group">
    <label>GitHub Token</label>
    <input type="password" name="github_token" id="github_token" placeholder="ghp_...">
  </div>
  <div class="form-row" style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
    <div class="form-group">
      <label>Owner</label>
      <input name="github_owner" id="github_owner" placeholder="your-username">
    </div>
    <div class="form-group">
      <label>TikTok Repo</label>
      <input name="tt_repo" id="tt_repo" placeholder="8dca7ff25e47b8cc0e104b9f-tt">
    </div>
  </div>
</div>
<div class="card">
  <h2>Stream Config</h2>
  <div class="form-group">
    <label>Source URL (YouTube, Twitch, etc.)</label>
    <input type="url" name="tt_url" id="tt_url" placeholder="https://www.youtube.com/watch?v=...">
  </div>
  <div class="form-group">
    <label>Restream RTMP URL</label>
    <div style="display:flex;gap:8px">
      <input type="text" name="tt_key" id="tt_key" placeholder="rtmp://live.restream.io/live/stream_key_XXXX" style="flex:1">
    </div>
    <div style="font-size:11px;color:#8b949e;margin-top:2px">
      Get from <a href="https://restream.io/streaming" target="_blank" style="color:#58a6ff">restream.io/streaming</a> — add TikTok as a channel in Restream<br>
      Free plan: 720p, Restream watermark. Paste full RTMP URL including stream key.
    </div>
  </div>
    <div class="form-group">
      <label>Overlay Text (displayed on stream)</label>
      <div style="display:flex;gap:8px">
        <input type="text" name="overlay_text" id="overlay_text" placeholder="Live on TikTok!" style="flex:1">
        <button class="btn btn-grey btn-sm" onclick="pushOverlay()" style="white-space:nowrap">Push Overlay</button>
      </div>
    </div>
    <div class="form-group">
      <label>Browser Overlay URL (Fusion Chat, alerts, counters, etc.)</label>
      <input type="url" name="browser_overlay_url" id="browser_overlay_url" placeholder="https://kicktools.app/fusion_chat/fusion-chat.html?kick=...">
      <div style="font-size:11px;color:#8b949e;margin-top:2px">Generate one at <a href="/chat" style="color:#58a6ff">Chat Overlay Generator</a> or paste any widget URL</div>
    </div>
    <div class="form-group" style="margin-top:4px">
      <label style="display:flex;align-items:center;gap:8px">
        <input type="checkbox" name="tt_keepalive" id="tt_keepalive" onchange="saveConfig()" style="width:auto">
        Keep Alive (auto-restart after 6h)
      </label>
    </div>
    <div class="actions">
      <button class="btn btn-pink" id="btnGoLive" onclick="goLive()">▶ Go Live (TikTok)</button>
      <button class="btn btn-red" id="btnStop" onclick="stopStream()" disabled>⏹ Stop</button>
      <button class="btn btn-blue btn-sm" onclick="saveConfig()">💾 Save</button>
      <button class="btn btn-orange btn-sm" onclick="location.href='/preview'">👁 Preview</button>
      <button class="btn btn-grey btn-sm" onclick="testSource()">🔍 Test Source</button>
      <button class="btn btn-grey btn-sm" onclick="document.getElementById('envInput').click()">📄 Upload .env</button>
      <input type="file" id="envInput" accept=".env" style="display:none" onchange="uploadEnv(this.files[0])">
    </div>
    <div id="testResult" style="font-size:12px;color:#8b949e;margin-top:8px"></div>
</div>
<div class="card">
  <h2>Logs</h2>
  <div class="log-box" id="logBox">Waiting...</div>
</div>
</div>
<script>
function applyForm(c) {
  if (!c) return;
  for (const [k,v] of Object.entries(c)) {
    const el = document.getElementById(k);
    if (el) el.value = v;
  }
}
function readForm() {
  const d = {};
  document.querySelectorAll('input,textarea,select').forEach(el => {
    if (el.type === 'checkbox') d[el.name] = el.checked;
    else if (el.name) d[el.name] = el.value;
  });
  return d;
}
function saveConfig(cb) {
  fetch('/config', {method:'POST', body:JSON.stringify(readForm()), headers:{'Content-Type':'application/json'}})
    .then(r=>r.json()).then(d=>{ addLog('Config saved','ok'); if(cb) cb(); })
    .catch(e=>{ addLog('Save failed','err'); if(cb) cb(); });
}
function testSource() {
  const el = document.getElementById('testResult');
  el.textContent = 'Checking...';
  fetch('/tiktok/resolve').then(r=>r.json()).then(d=>{
    el.textContent = d.ok ? '✓ Live — HLS resolved' : '✗ Not live';
  }).catch(()=>el.textContent='✗ Failed');
}
function fetchTikTokKey() {
  alert('1. Go to https://restream.io/ → Sign up (free)\n2. Add TikTok as a channel\n3. Go to Streaming tab → copy RTMP URL\n4. Paste the full URL in the Restream RTMP URL field above');
}
function uploadEnv(file) {
  if (!file) return;
  const fd = new FormData();
  fd.append('env_file', file);
  addLog('Uploading .env...','info');
  fetch('/upload_env', {method:'POST', body:fd})
    .then(r=>r.json()).then(d=>{
      addLog(d.ok ? '.env uploaded successfully' : 'Error: '+d.error, d.ok?'ok':'err');
      if(d.ok) setTimeout(()=>location.reload(), 1500);
    }).catch(e=>addLog('Upload failed','err'));
}
function goLive() {
  document.getElementById('btnGoLive').disabled = true;
  addLog('Starting TikTok stream...','info');
  saveConfig(() => {
    fetch('/tiktok/start').then(r=>r.json()).then(d=>{
      if(!d.ok) { addLog('Error: '+d.error,'err'); document.getElementById('btnGoLive').disabled = false; }
    }).catch(e=>{ addLog('Start failed','err'); document.getElementById('btnGoLive').disabled = false; });
  });
}
function stopStream() {
  document.getElementById('btnStop').disabled = true;
  addLog('Stopping...','warn');
  fetch('/tiktok/stop').then(r=>r.json()).then(d=>{
    addLog(d.ok ? 'Stopped' : 'Error: '+d.error, d.ok ? 'warn' : 'err');
  }).catch(e=>addLog('Stop failed','err'));
}
function pushOverlay() {
  saveConfig(() => addLog('Overlay pushed','ok'));
}
function fetchFMAtracks() {
  const url = document.getElementById('fmaUrl').value.trim();
  if (!url) { addLog('Enter an FMA album URL first','err'); return; }
  addLog('Fetching tracks from FMA...','info');
  fetch('/fma_parse', {method:'POST', body:JSON.stringify({url}), headers:{'Content-Type':'application/json'}})
    .then(r=>r.json()).then(d=>{
      if (!d.ok) { addLog('Error: '+d.error,'err'); return; }
      addLog('Loaded '+d.count+' tracks from FMA','ok');
      saveConfig();
    }).catch(e=>addLog('Fetch failed','err'));
}
function addLog(msg,cls='info') {
  const box = document.getElementById('logBox');
  box.innerHTML += '<span class="'+cls+'">['+new Date().toLocaleTimeString()+'] '+msg+'</span>\n';
  box.scrollTop = box.scrollHeight;
}
function updateStatus() {
  fetch('/tiktok/status').then(r=>r.json()).then(d=>{
    const dot = document.getElementById('statusDot');
    const txt = document.getElementById('statusText');
    if(d.live) {
      dot.className = 'status-dot live';
      txt.textContent = '● LIVE' + (d.keepalive ? ' (auto-restart)' : '');
      document.getElementById('btnGoLive').disabled = true;
      document.getElementById('btnStop').disabled = false;
    } else {
      dot.className = 'status-dot stopped';
      txt.textContent = '○ Stopped';
      document.getElementById('btnGoLive').disabled = false;
      document.getElementById('btnStop').disabled = true;
    }
    if(d.config) document.getElementById('tt_keepalive').checked = d.config.tt_keepalive;
  }).catch(()=>{});
}
function fetchLogs() {
  fetch('/logs').then(r=>r.text()).then(t=>{
    const box = document.getElementById('logBox');
    if(t) box.innerHTML = t;
    box.scrollTop = box.scrollHeight;
  }).catch(()=>{});
}
fetch('/tiktok/status').then(r=>r.json()).then(d=>{ if(d.config) applyForm(d.config); });
setInterval(updateStatus, 3000);
setInterval(fetchLogs, 2000);
</script>
</body>
</html>'''

HTML_FB_PANEL = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Facebook Stream Panel</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',sans-serif;background:#0d1117;color:#c9d1d9}
.container{max-width:900px;margin:0 auto;padding:20px}
h1{font-size:22px;margin-bottom:20px;color:#fff}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:20px;margin-bottom:16px}
.card h2{font-size:16px;margin-bottom:12px;color:#f0f6fc}
.form-group{margin-bottom:12px}
.form-group label{display:block;font-size:13px;color:#8b949e;margin-bottom:4px}
.form-group input,.form-group textarea,.form-group select{width:100%;padding:8px 12px;background:#0d1117;border:1px solid #30363d;border-radius:6px;color:#c9d1d9;font-size:14px}
.form-group input:focus,.form-group select:focus,.form-group textarea:focus{outline:none;border-color:#58a6ff}
.form-group textarea{resize:vertical;min-height:60px}
.btn{display:inline-flex;align-items:center;gap:8px;padding:10px 24px;border:none;border-radius:6px;font-size:15px;font-weight:600;cursor:pointer}
.btn:disabled{opacity:.5;cursor:not-allowed}
.btn-blue{background:#1877f2;color:#fff}
.btn-blue:hover:not(:disabled){background:#3b8af2}
.btn-red{background:#da3633;color:#fff}
.btn-red:hover:not(:disabled){background:#f85149}
.btn-grey{background:#21262d;color:#c9d1d9;border:1px solid #30363d}
.btn-grey:hover:not(:disabled){background:#30363d}
.btn-orange{background:#d29922;color:#fff}
.btn-orange:hover:not(:disabled){background:#e3b341}
.btn-sm{padding:6px 14px;font-size:13px}
.actions{display:flex;gap:12px;margin:12px 0;flex-wrap:wrap}
.status-bar{display:flex;align-items:center;gap:16px;padding:12px 16px;background:#0d1117;border:1px solid #30363d;border-radius:6px;margin-bottom:16px}
.status-dot{width:10px;height:10px;border-radius:50%;display:inline-block;margin-right:6px}
.status-dot.live{background:#3fb950;box-shadow:0 0 8px #3fb950}
.status-dot.stopped{background:#f85149}
.log-box{background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:12px;height:300px;overflow-y:auto;font-family:monospace;font-size:12px;line-height:1.5;white-space:pre-wrap}
.log-box .info{color:#8b949e}
.log-box .err{color:#f85149}
.log-box .ok{color:#3fb950}
</style>
</head>
<body>
<div class="container">
<div style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap">
  <a href="/" style="padding:8px 16px;background:#30363d;color:#c9d1d9;border-radius:6px;text-decoration:none;font-size:14px">Kick</a>
  <a href="/yt" style="padding:8px 16px;background:#30363d;color:#c9d1d9;border-radius:6px;text-decoration:none;font-size:14px">YouTube</a>
  <a href="/twitch" style="padding:8px 16px;background:#30363d;color:#c9d1d9;border-radius:6px;text-decoration:none;font-size:14px">Twitch</a>
  <a href="/tiktok" style="padding:8px 16px;background:#30363d;color:#c9d1d9;border-radius:6px;text-decoration:none;font-size:14px">TikTok</a>
  <a href="/facebook" style="padding:8px 16px;background:#1f6feb;color:#fff;border-radius:6px;text-decoration:none;font-size:14px;font-weight:600">Facebook</a>
  <a href="/chat" style="padding:8px 16px;background:#30363d;color:#c9d1d9;border-radius:6px;text-decoration:none;font-size:14px">Chat</a>
</div>
<h1>Facebook Stream Panel</h1>
<div class="status-bar">
  <span><span class="status-dot" id="statusDot"></span><span class="status-text" id="statusText">Checking...</span></span>
</div>
<div class="card">
  <h2>GitHub Config</h2>
  <div class="form-group">
    <label>GitHub Token</label>
    <input type="password" name="github_token" id="github_token" placeholder="ghp_...">
  </div>
  <div class="form-row" style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
    <div class="form-group">
      <label>Owner</label>
      <input name="github_owner" id="github_owner" placeholder="your-username">
    </div>
    <div class="form-group">
      <label>FB Repo</label>
      <input name="fb_repo" id="fb_repo" placeholder="8dca7ff25e47b8cc0e104b9f-fb">
    </div>
  </div>
</div>
<div class="card">
  <h2>Stream Config</h2>
  <div class="form-group">
    <label>Source URL (Twitch)</label>
    <input type="url" name="fb_url" id="fb_url" placeholder="https://www.twitch.tv/streamer">
  </div>
  <div class="form-group">
    <label>Facebook Stream Key</label>
    <input type="text" name="fb_key" id="fb_key" placeholder="From facebook.com/live/producer">
    <div style="font-size:11px;color:#8b949e;margin-top:2px">Get it at <a href="https://facebook.com/live/producer" target="_blank" style="color:#58a6ff">facebook.com/live/producer</a></div>
  </div>
    <div class="form-group">
      <label>Overlay Text (displayed on stream)</label>
      <div style="display:flex;gap:8px">
        <input type="text" name="overlay_text" id="overlay_text" placeholder="Live on Facebook!" style="flex:1">
        <button class="btn btn-grey btn-sm" onclick="pushOverlay()" style="white-space:nowrap">Push Overlay</button>
      </div>
    </div>
    <div class="form-group">
      <label>Browser Overlay URL (Fusion Chat, alerts, counters, etc.)</label>
      <input type="url" name="browser_overlay_url" id="browser_overlay_url" placeholder="https://kicktools.app/fusion_chat/fusion-chat.html?kick=...">
      <div style="font-size:11px;color:#8b949e;margin-top:2px">Generate one at <a href="/chat" style="color:#58a6ff">Chat Overlay Generator</a> or paste any widget URL</div>
    </div>
    <div class="form-group" style="margin-top:4px">
      <label style="display:flex;align-items:center;gap:8px">
        <input type="checkbox" name="fb_keepalive" id="fb_keepalive" onchange="saveConfig()" style="width:auto">
        Keep Alive (auto-restart after 6h)
      </label>
    </div>
    <div class="actions">
      <button class="btn btn-blue" id="btnGoLive" onclick="goLive()">▶ Go Live (Facebook)</button>
      <button class="btn btn-red" id="btnStop" onclick="stopStream()" disabled>⏹ Stop</button>
      <button class="btn btn-grey btn-sm" onclick="saveConfig()">💾 Save</button>
      <button class="btn btn-orange btn-sm" onclick="location.href='/preview'">👁 Preview</button>
      <button class="btn btn-grey btn-sm" onclick="testSource()">🔍 Test Source</button>
      <button class="btn btn-grey btn-sm" onclick="document.getElementById('envInput').click()">📄 Upload .env</button>
      <input type="file" id="envInput" accept=".env" style="display:none" onchange="uploadEnv(this.files[0])">
    </div>
    <div id="testResult" style="font-size:12px;color:#8b949e;margin-top:8px"></div>
</div>
<div class="card">
  <h2>Logs</h2>
  <div class="log-box" id="logBox">Waiting...</div>
</div>
</div>
<script>
function applyForm(c) {
  if (!c) return;
  for (const [k,v] of Object.entries(c)) {
    const el = document.getElementById(k);
    if (el) el.value = v;
  }
}
function readForm() {
  const d = {};
  document.querySelectorAll('input,textarea,select').forEach(el => {
    if (el.type === 'checkbox') d[el.name] = el.checked;
    else if (el.name) d[el.name] = el.value;
  });
  return d;
}
function saveConfig(cb) {
  fetch('/config', {method:'POST', body:JSON.stringify(readForm()), headers:{'Content-Type':'application/json'}})
    .then(r=>r.json()).then(d=>{ addLog('Config saved','ok'); if(cb) cb(); })
    .catch(e=>{ addLog('Save failed','err'); if(cb) cb(); });
}
function testSource() {
  const el = document.getElementById('testResult');
  el.textContent = 'Checking...';
  fetch('/facebook/resolve').then(r=>r.json()).then(d=>{
    el.textContent = d.ok ? '✓ Live — HLS resolved' : '✗ Not live';
  }).catch(()=>el.textContent='✗ Failed');
}
function uploadEnv(file) {
  if (!file) return;
  const fd = new FormData();
  fd.append('env_file', file);
  addLog('Uploading .env...','info');
  fetch('/upload_env', {method:'POST', body:fd})
    .then(r=>r.json()).then(d=>{
      addLog(d.ok ? '.env uploaded successfully' : 'Error: '+d.error, d.ok?'ok':'err');
      if(d.ok) setTimeout(()=>location.reload(), 1500);
    }).catch(e=>addLog('Upload failed','err'));
}
function goLive() {
  document.getElementById('btnGoLive').disabled = true;
  addLog('Starting Facebook stream...','info');
  saveConfig(() => {
    fetch('/facebook/start').then(r=>r.json()).then(d=>{
      if(!d.ok) { addLog('Error: '+d.error,'err'); document.getElementById('btnGoLive').disabled = false; }
    }).catch(e=>{ addLog('Start failed','err'); document.getElementById('btnGoLive').disabled = false; });
  });
}
function stopStream() {
  document.getElementById('btnStop').disabled = true;
  addLog('Stopping...','warn');
  fetch('/facebook/stop').then(r=>r.json()).then(d=>{
    addLog(d.ok ? 'Stopped' : 'Error: '+d.error, d.ok ? 'warn' : 'err');
  }).catch(e=>addLog('Stop failed','err'));
}
function pushOverlay() {
  saveConfig(() => addLog('Overlay pushed','ok'));
}
function fetchFMAtracks() {
  const url = document.getElementById('fmaUrl').value.trim();
  if (!url) { addLog('Enter an FMA album URL first','err'); return; }
  addLog('Fetching tracks from FMA...','info');
  fetch('/fma_parse', {method:'POST', body:JSON.stringify({url}), headers:{'Content-Type':'application/json'}})
    .then(r=>r.json()).then(d=>{
      if (!d.ok) { addLog('Error: '+d.error,'err'); return; }
      addLog('Loaded '+d.count+' tracks from FMA','ok');
      saveConfig();
    }).catch(e=>addLog('Fetch failed','err'));
}
function addLog(msg,cls='info') {
  const box = document.getElementById('logBox');
  box.innerHTML += '<span class="'+cls+'">['+new Date().toLocaleTimeString()+'] '+msg+'</span>\n';
  box.scrollTop = box.scrollHeight;
}
function updateStatus() {
  fetch('/facebook/status').then(r=>r.json()).then(d=>{
    const dot = document.getElementById('statusDot');
    const txt = document.getElementById('statusText');
    if(d.live) {
      dot.className = 'status-dot live';
      txt.textContent = '● LIVE' + (d.keepalive ? ' (auto-restart)' : '');
      document.getElementById('btnGoLive').disabled = true;
      document.getElementById('btnStop').disabled = false;
    } else {
      dot.className = 'status-dot stopped';
      txt.textContent = '○ Stopped';
      document.getElementById('btnGoLive').disabled = false;
      document.getElementById('btnStop').disabled = true;
    }
    if(d.config) document.getElementById('fb_keepalive').checked = d.config.fb_keepalive;
  }).catch(()=>{});
}
function fetchLogs() {
  fetch('/logs').then(r=>r.text()).then(t=>{
    const box = document.getElementById('logBox');
    if(t) box.innerHTML = t;
    box.scrollTop = box.scrollHeight;
  }).catch(()=>{});
}
fetch('/facebook/status').then(r=>r.json()).then(d=>{ if(d.config) applyForm(d.config); });
setInterval(updateStatus, 3000);
setInterval(fetchLogs, 2000);
</script>
</body>
</html>'''

HTML_FB_NOW_PANEL = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FB-Now Stream Panel</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',sans-serif;background:#0d1117;color:#c9d1d9}
.container{max-width:700px;margin:0 auto;padding:20px}
h1{font-size:22px;margin-bottom:20px;color:#fff}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:20px;margin-bottom:16px}
.card h2{font-size:16px;margin-bottom:12px;color:#e6edf3}
.form-group{margin-bottom:12px}
.form-group label{display:block;font-size:13px;color:#8b949e;margin-bottom:4px}
.form-group input,.form-group textarea{width:100%;padding:8px 12px;background:#0d1117;border:1px solid #30363d;border-radius:6px;color:#c9d1d9;font-size:14px}
.btn{padding:10px 20px;border:none;border-radius:6px;cursor:pointer;font-size:14px;font-weight:600}
.btn:disabled{opacity:0.5;cursor:not-allowed}
.btn-green{background:#3fb950;color:#fff}
.btn-green:hover:not(:disabled){background:#56d364}
.btn-red{background:#da3633;color:#fff}
.btn-red:hover:not(:disabled){background:#f85149}
.btn-grey{background:#21262d;color:#c9d1d9;border:1px solid #30363d}
.btn-grey:hover:not(:disabled){background:#30363d}
.btn-blue{background:#1f6feb;color:#fff}
.btn-blue:hover:not(:disabled){background:#388bfd}
.btn-sm{padding:6px 14px;font-size:13px}
.actions{display:flex;gap:12px;margin:12px 0;flex-wrap:wrap}
.status-bar{display:flex;align-items:center;gap:16px;padding:12px 16px;background:#0d1117;border:1px solid #30363d;border-radius:6px;margin-bottom:16px}
.status-dot{width:10px;height:10px;border-radius:50%;display:inline-block;margin-right:6px}
.status-dot.live{background:#3fb950;box-shadow:0 0 8px #3fb950}
.status-dot.stopped{background:#f85149}
.log-box{background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:12px;height:300px;overflow-y:auto;font-family:monospace;font-size:12px;line-height:1.5;white-space:pre-wrap}
.log-box .info{color:#8b949e}
.log-box .err{color:#f85149}
.log-box .ok{color:#3fb950}
</style>
</head>
<body>
<div class="container">
<div style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap">
  <a href="/" style="padding:8px 16px;background:#30363d;color:#c9d1d9;border-radius:6px;text-decoration:none;font-size:14px">Kick</a>
  <a href="/yt" style="padding:8px 16px;background:#30363d;color:#c9d1d9;border-radius:6px;text-decoration:none;font-size:14px">YouTube</a>
  <a href="/twitch" style="padding:8px 16px;background:#30363d;color:#c9d1d9;border-radius:6px;text-decoration:none;font-size:14px">Twitch</a>
  <a href="/tiktok" style="padding:8px 16px;background:#30363d;color:#c9d1d9;border-radius:6px;text-decoration:none;font-size:14px">TikTok</a>
  <a href="/facebook" style="padding:8px 16px;background:#30363d;color:#c9d1d9;border-radius:6px;text-decoration:none;font-size:14px">Facebook</a>
  <a href="/fb-now" style="padding:8px 16px;background:#1f6feb;color:#fff;border-radius:6px;text-decoration:none;font-size:14px;font-weight:600">FB-Now</a>
  <a href="/chat" style="padding:8px 16px;background:#30363d;color:#c9d1d9;border-radius:6px;text-decoration:none;font-size:14px">Chat</a>
</div>
<h1>FB-Now Stream Panel</h1>
<p style="color:#8b949e;font-size:13px;margin-bottom:16px">Direct source-to-Facebook restream (no fallback)</p>
<div class="status-bar">
  <span><span class="status-dot" id="statusDot"></span><span class="status-text" id="statusText">Checking...</span></span>
</div>
<div class="card">
  <h2>GitHub Config</h2>
  <div class="form-group">
    <label>GitHub Token</label>
    <input type="password" name="github_token" id="github_token" placeholder="ghp_...">
  </div>
  <div class="form-row" style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
    <div class="form-group">
      <label>Owner</label>
      <input name="github_owner" id="github_owner" placeholder="your-username">
    </div>
    <div class="form-group">
      <label>FB-Now Repo</label>
      <input name="fb_now_repo" id="fb_now_repo" placeholder="8dca7ff25e47b8cc0e104b9f-fb">
    </div>
  </div>
</div>
<div class="card">
  <h2>Stream Config</h2>
  <div class="form-group">
    <label>Source URLs (one per line — plays sequentially, ~30min each)</label>
    <textarea name="fb_now_sources" id="fb_now_sources" rows="5" placeholder="https://www.youtube.com/watch?v=VIDEO1&#10;https://www.youtube.com/watch?v=VIDEO2&#10;https://www.youtube.com/watch?v=VIDEO3" style="font-family:monospace;font-size:11px"></textarea>
    <div style="font-size:11px;color:#8b949e;margin-top:2px">Each source plays for the duration below, then auto-advances to next. Leave empty to use single Source URL below.</div>
  </div>
  <div class="form-group">
    <label>Single Source URL (fallback if list above is empty)</label>
    <input type="url" name="fb_now_url" id="fb_now_url" placeholder="YouTube, Twitch, Kick URL">
  </div>
  <div class="form-group">
    <label>Facebook Stream Key</label>
    <input type="text" name="fb_now_key" id="fb_now_key" placeholder="From facebook.com/live/producer">
    <div style="font-size:11px;color:#8b949e;margin-top:2px">Get it at <a href="https://facebook.com/live/producer" target="_blank" style="color:#58a6ff">facebook.com/live/producer</a></div>
  </div>
  <div class="form-group">
    <label>Source Duration (seconds per source)</label>
    <input type="number" name="fb_now_source_duration" id="fb_now_source_duration" value="1800" placeholder="1800">
    <div style="font-size:11px;color:#8b949e;margin-top:2px">Default 1800 (30 min). After this time, auto-advances to next source in queue.</div>
  </div>
  <div class="form-group">
    <label>Overlay Text (displayed on stream)</label>
    <div style="display:flex;gap:8px">
      <input type="text" name="overlay_text" id="overlay_text" placeholder="Live on Facebook!" style="flex:1">
      <button class="btn btn-grey btn-sm" onclick="pushOverlay()" style="white-space:nowrap">Push Overlay</button>
    </div>
  </div>
  <div class="form-group">
    <label>YouTube Cookies (for YouTube sources, paste Netscape cookies.txt)</label>
    <textarea name="fb_now_cookies" id="fb_now_cookies" rows="4" placeholder="Paste cookies.txt content here (export from browser)" style="font-family:monospace;font-size:11px"></textarea>
  </div>
  <div class="form-group" style="margin-top:4px">
    <label style="display:flex;align-items:center;gap:8px">
      <input type="checkbox" name="fb_now_chat_enabled" id="fb_now_chat_enabled" onchange="saveConfig()" style="width:auto">
      Enable Facebook Live Chat overlay
    </label>
    <div style="font-size:11px;color:#8b949e;margin-left:20px">Shows live comments from your FB stream on screen</div>
  </div>
  <div class="form-group">
    <label>Facebook Live Video ID</label>
    <input type="text" name="fb_live_video_id" id="fb_live_video_id" placeholder="From FB live producer page URL">
    <div style="font-size:11px;color:#8b949e;margin-top:2px">Find in the URL: facebook.com/live/producer/VIDEO_ID</div>
  </div>
  <div class="form-group">
    <label>Facebook Chat Access Token</label>
    <input type="text" name="fb_chat_token" id="fb_chat_token" placeholder="Page access token with pages_read_engagement">
  </div>
  <div class="form-group" style="margin-top:4px">
    <label style="display:flex;align-items:center;gap:8px">
      <input type="checkbox" name="fb_now_keepalive" id="fb_now_keepalive" onchange="saveConfig()" style="width:auto">
      Keep Alive (auto-restart after 6h)
    </label>
  </div>
  <div class="actions">
    <button class="btn btn-blue" id="btnGoLive" onclick="goLive()">▶ Go Live (FB-Now)</button>
    <button class="btn btn-red" id="btnStop" onclick="stopStream()" disabled>⏹ Stop</button>
    <button class="btn btn-grey btn-sm" onclick="saveConfig()">💾 Save</button>
    <button class="btn btn-grey btn-sm" onclick="testSource()">🔍 Test Source</button>
    <button class="btn btn-grey btn-sm" onclick="document.getElementById('envInput').click()">📄 Upload .env</button>
    <input type="file" id="envInput" accept=".env" style="display:none" onchange="uploadEnv(this.files[0])">
  </div>
  <div id="testResult" style="font-size:12px;color:#8b949e;margin-top:8px"></div>
</div>
<div class="card">
  <h2>Logs</h2>
  <div class="log-box" id="logBox">Waiting...</div>
</div>
</div>
<script>
function applyForm(c) {
  if (!c) return;
  for (const [k,v] of Object.entries(c)) {
    const el = document.getElementById(k);
    if (el) el.value = v;
  }
}
function readForm() {
  const d = {};
  document.querySelectorAll('input,textarea,select').forEach(el => {
    if (el.type === 'checkbox') d[el.name] = el.checked;
    else if (el.name) d[el.name] = el.value;
  });
  return d;
}
function saveConfig(cb) {
  fetch('/config', {method:'POST', body:JSON.stringify(readForm()), headers:{'Content-Type':'application/json'}})
    .then(r=>r.json()).then(d=>{ addLog('Config saved','ok'); if(cb) cb(); })
    .catch(e=>{ addLog('Save failed','err'); if(cb) cb(); });
}
function testSource() {
  const el = document.getElementById('testResult');
  el.textContent = 'Checking...';
  fetch('/fb-now/resolve').then(r=>r.json()).then(d=>{
    el.textContent = d.ok ? '✓ Live — HLS resolved' : '✗ Not live';
  }).catch(()=>el.textContent='✗ Failed');
}
function goLive() {
  document.getElementById('btnGoLive').disabled = true;
  addLog('Starting FB-Now stream...','info');
  saveConfig(() => {
    fetch('/fb-now/start').then(r=>r.json()).then(d=>{
      if(!d.ok) { addLog('Error: '+d.error,'err'); document.getElementById('btnGoLive').disabled = false; }
    }).catch(e=>{ addLog('Start failed','err'); document.getElementById('btnGoLive').disabled = false; });
  });
}
function stopStream() {
  document.getElementById('btnStop').disabled = true;
  addLog('Stopping...','warn');
  fetch('/fb-now/stop').then(r=>r.json()).then(d=>{
    addLog(d.ok ? 'Stopped' : 'Error: '+d.error, d.ok ? 'warn' : 'err');
  }).catch(e=>addLog('Stop failed','err'));
}
function pushOverlay() {
  saveConfig(() => addLog('Overlay pushed','ok'));
}
function uploadEnv(file) {
  if (!file) return;
  const fd = new FormData();
  fd.append('env_file', file);
  addLog('Uploading .env...','info');
  fetch('/upload_env', {method:'POST', body:fd})
    .then(r=>r.json()).then(d=>{
      addLog(d.ok ? '.env uploaded successfully' : 'Error: '+d.error, d.ok?'ok':'err');
      if(d.ok) setTimeout(()=>location.reload(), 1500);
    }).catch(e=>addLog('Upload failed','err'));
}
function addLog(msg,cls='info') {
  const box = document.getElementById('logBox');
  box.innerHTML += '<span class="'+cls+'">['+new Date().toLocaleTimeString()+'] '+msg+'</span>\n';
  box.scrollTop = box.scrollHeight;
}
function updateStatus() {
  fetch('/fb-now/status').then(r=>r.json()).then(d=>{
    const dot = document.getElementById('statusDot');
    const txt = document.getElementById('statusText');
    if(d.live) {
      dot.className = 'status-dot live';
      let status = '● LIVE';
      if(d.source_count > 1) status += ` (source ${d.source_index+1}/${d.source_count})`;
      if(d.keepalive) status += ' (auto-restart)';
      txt.textContent = status;
      document.getElementById('btnGoLive').disabled = true;
      document.getElementById('btnStop').disabled = false;
    } else {
      dot.className = 'status-dot stopped';
      txt.textContent = '○ Stopped';
      document.getElementById('btnGoLive').disabled = false;
      document.getElementById('btnStop').disabled = true;
    }
    if(d.config) document.getElementById('fb_now_keepalive').checked = d.config.fb_now_keepalive;
  }).catch(()=>{});
}
function fetchLogs() {
  fetch('/logs').then(r=>r.text()).then(t=>{
    const box = document.getElementById('logBox');
    if(t) box.innerHTML = t;
    box.scrollTop = box.scrollHeight;
  }).catch(()=>{});
}
fetch('/fb-now/status').then(r=>r.json()).then(d=>{ if(d.config) applyForm(d.config); });
setInterval(updateStatus, 3000);
setInterval(fetchLogs, 2000);
</script>
</body>
</html>'''

HTML_CHAT_PANEL = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Chat Overlay Generator</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',sans-serif;background:#0d1117;color:#c9d1d9}
.container{max-width:900px;margin:0 auto;padding:20px}
h1{font-size:22px;margin-bottom:20px;color:#fff}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:20px;margin-bottom:16px}
.card h2{font-size:16px;margin-bottom:12px;color:#f0f6fc}
.form-group{margin-bottom:12px}
.form-group label{display:block;font-size:13px;color:#8b949e;margin-bottom:4px}
.form-group input,.form-group textarea,.form-group select{width:100%;padding:8px 12px;background:#0d1117;border:1px solid #30363d;border-radius:6px;color:#c9d1d9;font-size:14px}
.form-group input:focus,.form-group select:focus{outline:none;border-color:#58a6ff}
.form-group input[type="checkbox"]{width:auto;margin-right:6px}
.form-row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.btn{display:inline-flex;align-items:center;gap:8px;padding:10px 24px;border:none;border-radius:6px;font-size:15px;font-weight:600;cursor:pointer}
.btn:disabled{opacity:.5;cursor:not-allowed}
.btn-green{background:#238636;color:#fff}
.btn-green:hover:not(:disabled){background:#2ea043}
.btn-purple{background:#7c3aed;color:#fff}
.btn-purple:hover:not(:disabled){background:#8b5cf6}
.btn-blue{background:#1f6feb;color:#fff}
.btn-blue:hover:not(:disabled){background:#388bfd}
.btn-grey{background:#21262d;color:#c9d1d9;border:1px solid #30363d}
.btn-grey:hover:not(:disabled){background:#30363d}
.btn-sm{padding:6px 14px;font-size:13px}
.url-box{background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:12px;font-family:monospace;font-size:13px;word-break:break-all;margin-top:12px;display:none}
.cls{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.cls label{display:flex;align-items:center;gap:4px;font-size:13px;cursor:pointer}
</style>
</head>
<body>
<div class="container">
<div style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap">
  <a href="/" style="padding:8px 16px;background:#30363d;color:#c9d1d9;border-radius:6px;text-decoration:none;font-size:14px">Kick</a>
  <a href="/yt" style="padding:8px 16px;background:#30363d;color:#c9d1d9;border-radius:6px;text-decoration:none;font-size:14px">YouTube</a>
  <a href="/twitch" style="padding:8px 16px;background:#30363d;color:#c9d1d9;border-radius:6px;text-decoration:none;font-size:14px">Twitch</a>
  <a href="/tiktok" style="padding:8px 16px;background:#30363d;color:#c9d1d9;border-radius:6px;text-decoration:none;font-size:14px">TikTok</a>
  <a href="/facebook" style="padding:8px 16px;background:#30363d;color:#c9d1d9;border-radius:6px;text-decoration:none;font-size:14px">Facebook</a>
  <a href="/fb-now" style="padding:8px 16px;background:#30363d;color:#c9d1d9;border-radius:6px;text-decoration:none;font-size:14px">FB-Now</a>
  <a href="/chat" style="padding:8px 16px;background:#7c3aed;color:#fff;border-radius:6px;text-decoration:none;font-size:14px;font-weight:600">Chat</a>
</div>
<h1>Chat Overlay Generator</h1>
<p style="color:#8b949e;font-size:14px;margin-bottom:16px">Generate a Fusion Chat overlay URL for OBS using <a href="https://kicktools.app/fusion_chat/" target="_blank" style="color:#58a6ff">kicktools.app</a></p>
<div class="card">
  <h2>Fusion Chat Setup</h2>
  <div class="form-row">
    <div class="form-group">
      <label>Kick Username</label>
      <input type="text" id="kick" placeholder="Type Kick username">
    </div>
    <div class="form-group">
      <label>Twitch Username</label>
      <input type="text" id="twitch" placeholder="Type Twitch username">
    </div>
  </div>
  <div class="form-row">
    <div class="form-group">
      <label>Font</label>
      <select id="font">
        <option value="Asap Condensed">Asap Condensed</option>
        <option value="Barlow Condensed">Barlow Condensed</option>
        <option value="Caveat">Caveat</option>
        <option value="Charm">Charm</option>
        <option value="Crimson Text">Crimson Text</option>
        <option value="Dosis">Dosis</option>
        <option value="Exo">Exo</option>
        <option value="Inter" selected>Inter</option>
        <option value="Itim">Itim</option>
        <option value="Oswald">Oswald</option>
        <option value="Roboto">Roboto</option>
        <option value="Teko">Teko</option>
        <option value="Ubuntu">Ubuntu</option>
        <option value="Zilla Slab">Zilla Slab</option>
      </select>
    </div>
    <div class="form-group">
      <label>Font Size</label>
      <select id="fontSize">
        <option value="small">Small</option>
        <option value="medium">Medium</option>
        <option value="Large" selected>Large</option>
        <option value="x-large">X-Large</option>
        <option value="xx-large">XX-large</option>
      </select>
    </div>
  </div>
  <div class="form-row">
    <div class="form-group">
      <label>Font Shadow</label>
      <select id="fontShadow">
        <option value="shadow-na" selected>None</option>
        <option value="shadow-sm">Small</option>
        <option value="shadow-m">Medium</option>
        <option value="shadow-lg">Large</option>
      </select>
    </div>
    <div class="form-group">
      <label>Font Color</label>
      <input type="color" id="fontColor" value="#ffffff" style="width:100%;height:40px;padding:2px;background:#0d1117;border:1px solid #30363d;border-radius:6px;cursor:pointer">
    </div>
  </div>
  <div class="form-row">
    <div class="form-group">
      <label>Theme</label>
      <select id="theme">
        <option value="custom" selected>Customizable</option>
        <option value="background">Custom w/ Background</option>
        <option value="nofade">Custom no Fade-In</option>
        <option value="basic">Basic</option>
        <option value="frost">Frost</option>
        <option value="h1">Horizontal V1</option>
        <option value="h2">Horizontal V2</option>
        <option value="halloween">Halloween 1</option>
        <option value="kickgreen">Kick Brand</option>
        <option value="platform">Platform</option>
        <option value="twitch">Twitch Brand</option>
        <option value="vpink">Vibrant Pink</option>
      </select>
    </div>
    <div class="form-group">
      <label>Case Settings</label>
      <select id="fontCase">
        <option value="none" selected>Regular Case</option>
        <option value="lowercase">Lower Case</option>
        <option value="uppercase">Upper Case</option>
        <option value="capitalize">Capitalize</option>
      </select>
    </div>
  </div>
  <hr style="border:none;border-top:1px solid #30363d;margin:16px 0">
  <div class="cls">
    <label><input type="checkbox" id="timestamp" checked> Timestamp</label>
    <label><input type="checkbox" id="platformBadges" checked> Platform Badges</label>
    <label><input type="checkbox" id="userBadges" checked> User Badges</label>
    <label><input type="checkbox" id="bots" checked> Bots</label>
    <label><input type="checkbox" id="highlight" checked> Highlight @Messages</label>
    <label><input type="checkbox" id="fade" checked> Fade Messages</label>
    <label style="gap:2px"> <input type="number" id="fadeTime" value="30" style="width:60px;padding:4px 6px;background:#0d1117;border:1px solid #30363d;border-radius:4px;color:#c9d1d9;font-size:13px"> Seconds</label>
  </div>
  <div style="margin-top:16px;display:flex;gap:8px">
    <button class="btn btn-purple" onclick="generate()">Generate URL</button>
    <button class="btn btn-grey btn-sm" onclick="resetForm()">Reset</button>
  </div>
  <div class="url-box" id="urlBox">
    <div style="display:flex;gap:8px;align-items:center;margin-bottom:8px">
      <strong style="color:#f0f6fc;font-size:14px">Your Overlay URL</strong>
      <button class="btn btn-blue btn-sm" onclick="copyUrl()">Copy</button>
    </div>
    <code id="urlOutput" style="color:#58a6ff"></code>
  </div>
</div>
<div class="card">
  <h2>OBS Setup</h2>
  <ol style="padding-left:20px;color:#c9d1d9;font-size:14px;line-height:1.8">
    <li>In OBS, under Sources, click <strong>+</strong> and add a new <strong>Browser Source</strong></li>
    <li>Name it something like "Chat Overlay" and click OK</li>
    <li>Paste the generated URL into the URL field</li>
    <li><strong>Important:</strong> Use Width/Height to size the overlay — don't resize with the mouse (causes rendering issues)</li>
    <li>For Horizontal Themes: set Width to your canvas width (usually 1080) and Height to ~100</li>
    <li>Click OK and position the overlay</li>
  </ol>
</div>
</div>
<script>
function generate() {
  const base = 'https://kicktools.app/fusion_chat/fusion-chat.html';
  const p = new URLSearchParams();
  const kick = document.getElementById('kick').value.trim();
  const twitch = document.getElementById('twitch').value.trim();
  if (!kick && !twitch) { alert('Enter at least one username'); return; }
  if (kick) p.set('kick', kick);
  if (twitch) p.set('twitch', twitch);
  p.set('font', document.getElementById('font').value);
  p.set('fontSize', document.getElementById('fontSize').value);
  p.set('fontShadow', document.getElementById('fontShadow').value);
  p.set('fontColor', document.getElementById('fontColor').value);
  p.set('theme', document.getElementById('theme').value);
  p.set('fontCase', document.getElementById('fontCase').value);
  if (document.getElementById('timestamp').checked) p.set('timestamp', 'on');
  if (document.getElementById('platformBadges').checked) p.set('platformBadges', 'on');
  if (document.getElementById('userBadges').checked) p.set('userBadges', 'on');
  if (document.getElementById('bots').checked) p.set('bots', 'on');
  if (document.getElementById('highlight').checked) p.set('highlight', 'on');
  if (document.getElementById('fade').checked) { p.set('fade', 'on'); p.set('fadeTime', document.getElementById('fadeTime').value); }
  const url = base + '?' + p.toString();
  document.getElementById('urlOutput').textContent = url;
  document.getElementById('urlBox').style.display = 'block';
}
function copyUrl() {
  const url = document.getElementById('urlOutput').textContent;
  navigator.clipboard.writeText(url).then(() => {
    const btn = document.querySelector('.url-box .btn-blue');
    const orig = btn.textContent;
    btn.textContent = 'Copied!';
    setTimeout(() => btn.textContent = orig, 2000);
  }).catch(() => alert('Copy failed. Select and copy manually.'));
}
function resetForm() {
  document.querySelectorAll('input[type="text"]').forEach(e => e.value = '');
  document.getElementById('fontColor').value = '#ffffff';
  document.getElementById('font').value = 'Inter';
  document.getElementById('fontSize').value = 'Large';
  document.getElementById('fontShadow').value = 'shadow-na';
  document.getElementById('theme').value = 'custom';
  document.getElementById('fontCase').value = 'none';
  document.querySelectorAll('input[type="checkbox"]').forEach(c => c.checked = true);
  document.getElementById('fadeTime').value = '30';
  document.getElementById('urlBox').style.display = 'none';
}
</script>
</body>
</html>'''

# ── KICK Chill (standalone) ──────────────────────────────────────

@app.route('/kick-chill')
def kick_chill_index():
    return HTML_KICK_CHILL_PANEL

@app.route('/kick-chill/status')
def kick_chill_status():
    cfg = load_config()
    token = cfg.get('github_token')
    owner = cfg.get('github_owner')
    repo = cfg.get('kick_chill_repo')
    live = False
    run_id = None
    if token and owner and repo:
        url = f'https://api.github.com/repos/{owner}/{repo}/actions/workflows/stream.yml/runs?status=in_progress&per_page=1'
        headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github.v3+json'}
        try:
            r = requests.get(url, headers=headers, timeout=10)
            runs = r.json().get('workflow_runs', [])
            if runs:
                run_id = runs[0]['id']
                live = True
        except:
            pass
    return jsonify({'live': live, 'config': cfg, 'run_id': run_id, 'wanted': kick_chill_wanted})

@app.route('/kick-chill/start')
def kick_chill_start():
    global kick_chill_wanted
    cfg = load_config()
    url = cfg.get('kick_chill_url', '').strip()
    key = cfg.get('kick_chill_key', '').strip()
    if not url:
        return jsonify({'ok': False, 'error': 'Missing YouTube source URL'})
    if not key:
        return jsonify({'ok': False, 'error': 'Missing Kick stream key/URL'})
    msg, err = trigger_kick_chill_workflow(url, key)
    if err:
        return jsonify({'ok': False, 'error': err})
    kick_chill_wanted = True
    save_config(cfg)
    log('KICK Chill workflow triggered')
    return jsonify({'ok': True, 'msg': msg})

@app.route('/kick-chill/stop')
def kick_chill_stop():
    global kick_chill_wanted
    kick_chill_wanted = False
    cfg = load_config()
    save_config(cfg)
    token = cfg.get('github_token')
    owner = cfg.get('github_owner')
    repo = cfg.get('kick_chill_repo')
    if not token or not owner or not repo:
        return jsonify({'ok': False, 'error': 'GitHub not configured'})
    url = f'https://api.github.com/repos/{owner}/{repo}/actions/workflows/stream.yml/runs?status=in_progress&per_page=1'
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github.v3+json'}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        runs = r.json().get('workflow_runs', [])
        if runs:
            run_id = runs[0]['id']
            cancel_url = f'https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}/cancel'
            requests.post(cancel_url, headers=headers)
            log('KICK Chill workflow cancelled')
            return jsonify({'ok': True})
    except:
        pass
    return jsonify({'ok': False, 'error': 'No active run found'})

HTML_KICK_CHILL_PANEL = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>KICK Chill</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',sans-serif;background:#0a0a0a;color:#e0e0e0;min-height:100vh;display:flex;align-items:center;justify-content:center}
.card{background:#111;border:1px solid #2a2a2a;border-radius:16px;padding:32px;width:100%;max-width:520px;box-shadow:0 8px 32px rgba(0,0,0,.5)}
h1{font-size:28px;text-align:center;margin-bottom:8px;color:#53fc18}
.subtitle{text-align:center;color:#666;font-size:13px;margin-bottom:24px}
.status{text-align:center;margin-bottom:20px}
.dot{width:12px;height:12px;border-radius:50%;display:inline-block;margin-right:8px;vertical-align:middle}
.dot.live{background:#53fc18;box-shadow:0 0 12px #53fc18;animation:pulse 2s infinite}
.dot.off{background:#555}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}
label{display:block;font-size:12px;color:#888;margin-bottom:6px;text-transform:uppercase;letter-spacing:1px}
input[type="text"],textarea{width:100%;padding:12px 14px;background:#1a1a1a;border:1px solid #333;border-radius:10px;color:#e0e0e0;font-size:14px;outline:none;transition:border .2s}
input:focus,textarea:focus{border-color:#53fc18}
textarea{resize:vertical;min-height:60px;font-family:monospace;font-size:11px}
.field{margin-bottom:16px}
.btns{display:flex;gap:12px;margin-top:20px}
.btn{flex:1;padding:14px;border:none;border-radius:10px;font-size:15px;font-weight:700;cursor:pointer;transition:all .2s}
.btn-go{background:#53fc18;color:#000}
.btn-go:hover{background:#6fff3a;transform:scale(1.02)}
.btn-stop{background:#ff3333;color:#fff}
.btn-stop:hover{background:#ff5555;transform:scale(1.02)}
.btn:disabled{opacity:.3;cursor:not-allowed;transform:none}
.hint{font-size:11px;color:#555;margin-top:4px}
.hint a{color:#53fc18;text-decoration:none}
.log{margin-top:20px;background:#0d0d0d;border:1px solid #222;border-radius:10px;padding:12px;max-height:200px;overflow-y:auto;font-family:monospace;font-size:11px;line-height:1.6;white-space:pre-wrap;color:#888}
</style>
</head>
<body>
<div class="card">
  <h1>KICK Chill</h1>
  <p class="subtitle">Stream any YouTube video 24/7 to Kick</p>
  <div class="status">
    <span class="dot" id="dot"></span>
    <span id="statusText" style="font-size:13px">Checking...</span>
  </div>
  <div class="field">
    <label>YouTube URL</label>
    <input type="text" id="kc_url" placeholder="https://www.youtube.com/watch?v=...">
    <div class="hint">Live streams loop forever. Videos download then loop.</div>
  </div>
  <div class="field">
    <label>Kick Stream Key</label>
    <input type="text" id="kc_key" placeholder="rtmp://stream.kick.com/app/...">
    <div class="hint">Full RTMP URL or just the stream key</div>
  </div>
  <div class="field">
    <label>Overlay Text</label>
    <input type="text" id="overlay_text" placeholder="KICK Chill">
  </div>
  <div class="field">
    <label>YouTube Cookies</label>
    <textarea id="yt_cookies" rows="3" placeholder="Paste Netscape cookies.txt content (needed for bot detection bypass)"></textarea>
    <div class="hint">Export from Chrome via <a href="https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc" target="_blank">Get cookies.txt</a></div>
  </div>
  <div class="btns">
    <button class="btn btn-go" id="btnGo" onclick="goChill()">GO LIVE</button>
    <button class="btn btn-stop" id="btnStop" onclick="stopChill()" disabled>STOP</button>
  </div>
  <div class="log" id="logBox">Waiting...</div>
</div>
<script>
let pollTimer;
function goChill() {
  document.getElementById('btnGo').disabled = true;
  saveKC();
  fetch('/kick-chill/start').then(r=>r.json()).then(d=>{
    document.getElementById('logBox').textContent = d.ok ? 'Stream started!' : d.error;
    document.getElementById('btnGo').disabled = false;
    poll();
  }).catch(e=>{
    document.getElementById('logBox').textContent = 'Error: '+e;
    document.getElementById('btnGo').disabled = false;
  });
}
function stopChill() {
  document.getElementById('btnStop').disabled = true;
  fetch('/kick-chill/stop').then(r=>r.json()).then(d=>{
    document.getElementById('logBox').textContent = d.ok ? 'Stopped!' : d.error;
    document.getElementById('btnStop').disabled = false;
    poll();
  });
}
function saveKC() {
  const cfg = {
    kick_chill_url: document.getElementById('kc_url').value,
    kick_chill_key: document.getElementById('kc_key').value,
    overlay_text: document.getElementById('overlay_text').value,
    yt_cookies: document.getElementById('yt_cookies').value
  };
  fetch('/config', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(cfg)});
}
function poll() {
  fetch('/kick-chill/status').then(r=>r.json()).then(d=>{
    const dot = document.getElementById('dot');
    const txt = document.getElementById('statusText');
    if (d.live) {
      dot.className = 'dot live';
      txt.textContent = 'LIVE';
      txt.style.color = '#53fc18';
      document.getElementById('btnStop').disabled = false;
    } else {
      dot.className = 'dot off';
      txt.textContent = 'Offline';
      txt.style.color = '#666';
      document.getElementById('btnStop').disabled = true;
    }
    if (d.config) {
      if (d.config.kick_chill_url) document.getElementById('kc_url').value = d.config.kick_chill_url;
      if (d.config.kick_chill_key) document.getElementById('kc_key').value = d.config.kick_chill_key;
      if (d.config.overlay_text) document.getElementById('overlay_text').value = d.config.overlay_text;
      if (d.config.yt_cookies) document.getElementById('yt_cookies').value = d.config.yt_cookies;
    }
  });
}
poll();
pollTimer = setInterval(poll, 5000);
</script>
</body>
</html>'''

if __name__ == '__main__':
    init_wanted()
    app.run(host='0.0.0.0', port=8080, debug=False)
