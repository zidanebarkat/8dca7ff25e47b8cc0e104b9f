from flask import Flask, request, jsonify
import os, time, json, requests, threading

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
current_run_id = None
config_path = 'gh_config.json'
log_buffer = []
log_lock = threading.Lock()

def init_wanted():
    global wanted, yt_wanted, twt_wanted, tt_wanted, fb_wanted
    try:
        with open(config_path) as f:
            c = json.load(f)
            wanted = c.get('kick_wanted', False)
            yt_wanted = c.get('yt_wanted', False)
            twt_wanted = c.get('twt_wanted', False)
            tt_wanted = c.get('tt_wanted', False)
            fb_wanted = c.get('fb_wanted', False)
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
    'yt_repo': _ENV.get('YT_REPO', '8dca7ff25e47b8cc0e104b9f-yt'),
    'yt_keepalive': False,
    'twt_url': _ENV.get('TWT_URL', 'https://www.twitch.tv/kaicenat'),
    'twt_key': _ENV.get('TWT_KEY', ''),
    'twt_repo': _ENV.get('TWT_REPO', '8dca7ff25e47b8cc0e104b9f-twt'),
    'twt_keepalive': False,
    'twt_client_id': _ENV.get('TWT_CLIENT_ID', ''),
    'twt_token': _ENV.get('TWT_TOKEN', ''),
    'tt_url': _ENV.get('TT_URL', 'https://www.twitch.tv/kaicenat'),
    'tt_key': _ENV.get('TT_KEY', ''),
    'tt_repo': _ENV.get('TT_REPO', '8dca7ff25e47b8cc0e104b9f-tt'),
    'tt_keepalive': False,
    'fb_url': _ENV.get('FB_URL', 'https://www.twitch.tv/kaicenat'),
    'fb_key': _ENV.get('FB_KEY', ''),
    'fb_repo': _ENV.get('FB_REPO', '8dca7ff25e47b8cc0e104b9f-fb'),
    'fb_keepalive': False,
    'fallback_enabled': False,
    'fallback_video': _ENV.get('FALLBACK_VIDEO', 'https://cdn.pixabay.com/video/2025/10/23/311602_large.mp4'),
    'fallback_playlist': _ENV.get('FALLBACK_PLAYLIST', 'https://files.freemusicarchive.org/storage-freemusicarchive-org/tracks/yFLu7P69mDjxhW2aF5MS16GVCqpw4oCqSKw4eSVN.mp3,https://files.freemusicarchive.org/storage-freemusicarchive-org/tracks/Djej42Pty0GrF6VFUNzYPDxsuhCwgWzF9ZHWFsZY.mp3,https://files.freemusicarchive.org/storage-freemusicarchive-org/tracks/wuk3O930psKilYVATDrGLTiu5RpokFDrza69zKb9.mp3,https://files.freemusicarchive.org/storage-freemusicarchive-org/tracks/0FIn9jCJbW1dgviRdVqoJWsyBCmfPZtgfNmlhy3u.mp3,https://files.freemusicarchive.org/storage-freemusicarchive-org/tracks/O6KDPWo1JOIOwsdqMIA4kidFWmy029ZvVjQDJngh.mp3,https://files.freemusicarchive.org/storage-freemusicarchive-org/tracks/2vMps2c9OEHdkncSObxKRhBtrY5tPKRxROyIM3Kw.mp3,https://files.freemusicarchive.org/storage-freemusicarchive-org/tracks/Bki0dtfe4SfgBMxIBMOaXcuePHGCLbaL7QjZAcH4.mp3'),
    'overlay_text': '',
    'browser_overlay_url': '',
    'kick_wanted': False,
    'yt_wanted': False,
    'twt_wanted': False,
    'tt_wanted': False,
    'fb_wanted': False,
}

wanted = False
yt_wanted = False
twt_wanted = False
tt_wanted = False
fb_wanted = False

def load_config():
    try:
        with open(config_path) as f:
            return json.load(f)
    except:
        return dict(DEFAULTS)

def save_config(cfg):
    global wanted, yt_wanted, twt_wanted, tt_wanted, fb_wanted
    cfg['kick_wanted'] = wanted
    cfg['yt_wanted'] = yt_wanted
    cfg['twt_wanted'] = twt_wanted
    cfg['tt_wanted'] = tt_wanted
    cfg['fb_wanted'] = fb_wanted
    with open(config_path, 'w') as f:
        json.dump(cfg, f)

def log(msg):
    with log_lock:
        ts = time.strftime('%H:%M:%S')
        log_buffer.append(f'[{ts}] {msg}')
        if len(log_buffer) > 200:
            log_buffer[:] = log_buffer[-200:]

def trigger_workflow(source_url, output_url):
    cfg = load_config()
    token = cfg.get('github_token') or GITHUB_TOKEN
    owner = cfg.get('github_owner') or GITHUB_OWNER
    repo = cfg.get('github_repo') or GITHUB_REPO
    if not token or not owner or not repo:
        return None, 'Missing GitHub config'
    url = f'https://api.github.com/repos/{owner}/{repo}/actions/workflows/restream.yml/dispatches'
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github.v3+json'}
    inputs = {
        'source_url': source_url,
        'output_url': output_url,
        'fallback_video': cfg.get('fallback_video', ''),
        'fallback_playlist': cfg.get('fallback_playlist', ''),
        'overlay_text': cfg.get('overlay_text', ''),
        'browser_overlay_url': cfg.get('browser_overlay_url', ''),
        'github_token': token,
    }
    data = {'ref': 'main', 'inputs': inputs}
    r = requests.post(url, json=data, headers=headers)
    if r.status_code not in (204, 201, 200):
        return None, f'GitHub API error: {r.status_code} {r.text[:200]}'
    return 'triggered', None

def trigger_yt_workflow(source_url, youtube_key):
    cfg = load_config()
    token = cfg.get('github_token') or GITHUB_TOKEN
    owner = cfg.get('github_owner') or GITHUB_OWNER
    repo = cfg.get('yt_repo') or '8dca7ff25e47b8cc0e104b9f-yt'
    if not token or not owner or not repo:
        return None, 'Missing GitHub config'
    url = f'https://api.github.com/repos/{owner}/{repo}/actions/workflows/restream.yml/dispatches'
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github.v3+json'}
    inputs = {
        'source_url': source_url,
        'youtube_key': youtube_key,
        'fallback_video': cfg.get('fallback_video', ''),
        'fallback_playlist': cfg.get('fallback_playlist', ''),
        'overlay_text': cfg.get('overlay_text', ''),
        'browser_overlay_url': cfg.get('browser_overlay_url', ''),
        'github_token': token,
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
    owner = cfg.get('github_owner') or GITHUB_OWNER
    repo = cfg.get('twt_repo') or '8dca7ff25e47b8cc0e104b9f-twt'
    if not token or not owner or not repo:
        return None, 'Missing GitHub config'
    url = f'https://api.github.com/repos/{owner}/{repo}/actions/workflows/restream.yml/dispatches'
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github.v3+json'}
    inputs = {
        'source_url': source_url,
        'twitch_key': twitch_key,
        'fallback_video': cfg.get('fallback_video', ''),
        'fallback_playlist': cfg.get('fallback_playlist', ''),
        'overlay_text': cfg.get('overlay_text', ''),
        'browser_overlay_url': cfg.get('browser_overlay_url', ''),
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
    inputs = {
        'source_url': source_url,
        'tiktok_key': tiktok_key,
        'fallback_video': cfg.get('fallback_video', ''),
        'fallback_playlist': cfg.get('fallback_playlist', ''),
        'overlay_text': cfg.get('overlay_text', ''),
        'browser_overlay_url': cfg.get('browser_overlay_url', ''),
        'github_token': token,
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
    inputs = {
        'source_url': source_url,
        'facebook_key': facebook_key,
        'fallback_video': cfg.get('fallback_video', ''),
        'fallback_playlist': cfg.get('fallback_playlist', ''),
        'overlay_text': cfg.get('overlay_text', ''),
        'browser_overlay_url': cfg.get('browser_overlay_url', ''),
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
    for k in DEFAULTS:
        if k in data:
            cfg[k] = data[k]
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
    msg, err = trigger_workflow(cfg['source_url'], cfg.get('output_url',''))
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
    if cfg.get('fallback_enabled') and cfg.get('fallback_video'):
        return cfg['fallback_video'], True
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
    if not cfg.get('twt_key'):
        return jsonify({'ok': False, 'error': 'Missing Twitch stream key'})
    msg, err = trigger_twt_workflow(cfg['twt_url'], cfg.get('twt_key',''))
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

@app.route('/chat')
def chat_index():
    return HTML_CHAT_PANEL

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
    <input type="url" name="source_url" id="source_url" placeholder="https://www.twitch.tv/streamer">
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
      <button class="btn btn-grey btn-sm" onclick="testSource()">🔍 Test Source</button>
      <button class="btn btn-grey btn-sm" onclick="document.getElementById('envInput').click()">📄 Upload .env</button>
      <input type="file" id="envInput" accept=".env" style="display:none" onchange="uploadEnv(this.files[0])">
    </div>
    <div id="testResult" style="font-size:12px;color:#8b949e;margin-top:8px"></div>
</div>
<div class="card">
  <h2>Fallback (when source is offline)</h2>
  <div class="form-group">
    <label style="display:flex;align-items:center;gap:8px">
      <input type="checkbox" name="fallback_enabled" id="fallback_enabled" onchange="saveConfig()" style="width:auto">
      Enable fallback background
    </label>
  </div>
  <div class="form-group">
    <label>Background Video URL</label>
    <input type="url" name="fallback_video" id="fallback_video" placeholder="https://cdn.pixabay.com/video/...">
  </div>
  <div class="form-group">
    <label>Music Playlist (one URL per line — MP3, YouTube, SoundCloud, or FMA album link)</label>
    <textarea name="fallback_playlist" id="fallback_playlist" rows="3" placeholder="https://files.freemusicarchive.org/..."></textarea>
  </div>
  <div style="display:flex;gap:8px;align-items:center">
    <input type="url" id="fmaUrl" placeholder="https://freemusicarchive.org/music/..." style="flex:1;padding:8px 12px;background:#0d1117;border:1px solid #30363d;border-radius:6px;color:#c9d1d9;font-size:13px">
    <button class="btn btn-grey btn-sm" onclick="fetchFMAtracks()">Fetch from FMA</button>
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
  document.getElementById('btnGoLive').disabled = true;
  addLog('Starting all outputs...','info');
  saveConfig(() => {
    fetch('/start').then(r=>r.json()).then(d=>{
      if(!d.ok) { addLog('Error: '+d.error,'err'); document.getElementById('btnGoLive').disabled = false; }
    }).catch(e=>{ addLog('Start failed','err'); document.getElementById('btnGoLive').disabled = false; });
  });
}

function stopStream() {
  document.getElementById('btnStop').disabled = true;
  addLog('Stopping...','warn');
  fetch('/stop').then(r=>r.json()).then(d=>{
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
      document.getElementById('fallback_playlist').value = d.tracks.join('\n');
      addLog('Loaded '+d.count+' tracks from FMA','ok');
      saveConfig();
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
    <label>Source URL (Twitch)</label>
    <input type="url" name="twt_url" id="twt_url" placeholder="https://www.twitch.tv/streamer">
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
      <button class="btn btn-grey btn-sm" onclick="testSource()">🔍 Test Source</button>
      <button class="btn btn-grey btn-sm" onclick="document.getElementById('envInput').click()">📄 Upload .env</button>
      <input type="file" id="envInput" accept=".env" style="display:none" onchange="uploadEnv(this.files[0])">
    </div>
    <div id="testResult" style="font-size:12px;color:#8b949e;margin-top:8px"></div>
</div>
<div class="card">
  <h2>Fallback (when source is offline)</h2>
  <div class="form-group">
    <label style="display:flex;align-items:center;gap:8px">
      <input type="checkbox" name="fallback_enabled" id="fallback_enabled" onchange="saveConfig()" style="width:auto">
      Enable fallback background
    </label>
  </div>
  <div class="form-group">
    <label>Background Video URL</label>
    <input type="url" name="fallback_video" id="fallback_video" placeholder="https://cdn.pixabay.com/video/...">
  </div>
  <div class="form-group">
    <label>Music Playlist (one URL per line — MP3, YouTube, SoundCloud, or FMA album link)</label>
    <textarea name="fallback_playlist" id="fallback_playlist" rows="3" placeholder="https://files.freemusicarchive.org/..."></textarea>
  </div>
  <div style="display:flex;gap:8px;align-items:center">
    <input type="url" id="fmaUrl" placeholder="https://freemusicarchive.org/music/..." style="flex:1;padding:8px 12px;background:#0d1117;border:1px solid #30363d;border-radius:6px;color:#c9d1d9;font-size:13px">
    <button class="btn btn-grey btn-sm" onclick="fetchFMAtracks()">Fetch from FMA</button>
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
      document.getElementById('fallback_playlist').value = d.tracks.join('\n');
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
      <label>Overlay Text (displayed on stream)</label>
      <div style="display:flex;gap:8px">
        <input type="text" name="overlay_text" id="overlay_text" placeholder="Live on YouTube!" style="flex:1">
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
        <input type="checkbox" name="yt_keepalive" id="yt_keepalive" onchange="saveConfig()" style="width:auto">
        Keep Alive (auto-restart after 6h)
      </label>
    </div>
    <div class="actions">
      <button class="btn btn-red" id="btnGoLive" onclick="goLive()" style="background:#ff0000;color:#fff">▶ Go Live (YouTube)</button>
      <button class="btn btn-red" id="btnStop" onclick="stopStream()" disabled>⏹ Stop</button>
      <button class="btn btn-blue btn-sm" onclick="saveConfig()">💾 Save</button>
      <button class="btn btn-grey btn-sm" onclick="testSource()">🔍 Test Source</button>
      <button class="btn btn-grey btn-sm" onclick="document.getElementById('envInput').click()">📄 Upload .env</button>
      <input type="file" id="envInput" accept=".env" style="display:none" onchange="uploadEnv(this.files[0])">
    </div>
    <div id="testResult" style="font-size:12px;color:#8b949e;margin-top:8px"></div>
</div>
<div class="card">
  <h2>Fallback (when source is offline)</h2>
  <div class="form-group">
    <label style="display:flex;align-items:center;gap:8px">
      <input type="checkbox" name="fallback_enabled" id="fallback_enabled" onchange="saveConfig()" style="width:auto">
      Enable fallback background
    </label>
  </div>
  <div class="form-group">
    <label>Background Video URL</label>
    <input type="url" name="fallback_video" id="fallback_video" placeholder="https://cdn.pixabay.com/video/...">
  </div>
  <div class="form-group">
    <label>Music Playlist (one URL per line — MP3, YouTube, SoundCloud, or FMA album link)</label>
    <textarea name="fallback_playlist" id="fallback_playlist" rows="3" placeholder="https://files.freemusicarchive.org/..."></textarea>
  </div>
  <div style="display:flex;gap:8px;align-items:center">
    <input type="url" id="fmaUrl" placeholder="https://freemusicarchive.org/music/..." style="flex:1;padding:8px 12px;background:#0d1117;border:1px solid #30363d;border-radius:6px;color:#c9d1d9;font-size:13px">
    <button class="btn btn-grey btn-sm" onclick="fetchFMAtracks()">Fetch from FMA</button>
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
      document.getElementById('fallback_playlist').value = d.tracks.join('\n');
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
  <a href="/chat" style="padding:8px 16px;background:#30363d;color:#c9d1d9;border-radius:6px;text-decoration:none;font-size:14px">Chat</a>
</div>
<h1>TikTok Stream Panel</h1>
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
    <label>Source URL (Twitch)</label>
    <input type="url" name="tt_url" id="tt_url" placeholder="https://www.twitch.tv/streamer">
  </div>
  <div class="form-group">
    <label>TikTok Stream Key</label>
    <div style="display:flex;gap:8px">
      <input type="text" name="tt_key" id="tt_key" placeholder="From livecenter.tiktok.com/producer" style="flex:1">
      <button class="btn btn-grey btn-sm" onclick="fetchTikTokKey()" style="white-space:nowrap">🤖 Auto-Fetch</button>
    </div>
    <div style="font-size:11px;color:#8b949e;margin-top:2px">
      Get key manually at <a href="https://livecenter.tiktok.com/producer" target="_blank" style="color:#58a6ff">livecenter.tiktok.com/producer</a> — key expires after 2 hours<br>
      Or run <code style="background:#21262d;padding:1px 4px;border-radius:3px">python tiktok_automation.py</code> locally to auto-fetch
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
      <button class="btn btn-grey btn-sm" onclick="testSource()">🔍 Test Source</button>
      <button class="btn btn-grey btn-sm" onclick="document.getElementById('envInput').click()">📄 Upload .env</button>
      <input type="file" id="envInput" accept=".env" style="display:none" onchange="uploadEnv(this.files[0])">
    </div>
    <div id="testResult" style="font-size:12px;color:#8b949e;margin-top:8px"></div>
</div>
<div class="card">
  <h2>Fallback (when source is offline)</h2>
  <div class="form-group">
    <label style="display:flex;align-items:center;gap:8px">
      <input type="checkbox" name="fallback_enabled" id="fallback_enabled" onchange="saveConfig()" style="width:auto">
      Enable fallback background
    </label>
  </div>
  <div class="form-group">
    <label>Background Video URL</label>
    <input type="url" name="fallback_video" id="fallback_video" placeholder="https://cdn.pixabay.com/video/...">
  </div>
  <div class="form-group">
    <label>Music Playlist (one URL per line — MP3, YouTube, SoundCloud, or FMA album link)</label>
    <textarea name="fallback_playlist" id="fallback_playlist" rows="3" placeholder="https://files.freemusicarchive.org/..."></textarea>
  </div>
  <div style="display:flex;gap:8px;align-items:center">
    <input type="url" id="fmaUrl" placeholder="https://freemusicarchive.org/music/..." style="flex:1;padding:8px 12px;background:#0d1117;border:1px solid #30363d;border-radius:6px;color:#c9d1d9;font-size:13px">
    <button class="btn btn-grey btn-sm" onclick="fetchFMAtracks()">Fetch from FMA</button>
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
  fetch('/tiktok/resolve').then(r=>r.json()).then(d=>{
    el.textContent = d.ok ? '✓ Live — HLS resolved' : '✗ Not live';
  }).catch(()=>el.textContent='✗ Failed');
}
function fetchTikTokKey() {
  addLog('Opening instruction...','info');
  alert('Run this on your LOCAL computer:\n\n1. pip install playwright\n2. playwright install chromium\n3. python tiktok_automation.py\n\nIt will open a browser, let you log into TikTok, and auto-fetch the stream key.\n\nThe key will be sent to this panel automatically.');
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
      document.getElementById('fallback_playlist').value = d.tracks.join('\n');
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
  <a href="/facebook" style="padding:8px 16px;background:#1877f2;color:#fff;border-radius:6px;text-decoration:none;font-size:14px;font-weight:600">Facebook</a>
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
      <button class="btn btn-grey btn-sm" onclick="testSource()">🔍 Test Source</button>
      <button class="btn btn-grey btn-sm" onclick="document.getElementById('envInput').click()">📄 Upload .env</button>
      <input type="file" id="envInput" accept=".env" style="display:none" onchange="uploadEnv(this.files[0])">
    </div>
    <div id="testResult" style="font-size:12px;color:#8b949e;margin-top:8px"></div>
</div>
<div class="card">
  <h2>Fallback (when source is offline)</h2>
  <div class="form-group">
    <label style="display:flex;align-items:center;gap:8px">
      <input type="checkbox" name="fallback_enabled" id="fallback_enabled" onchange="saveConfig()" style="width:auto">
      Enable fallback background
    </label>
  </div>
  <div class="form-group">
    <label>Background Video URL</label>
    <input type="url" name="fallback_video" id="fallback_video" placeholder="https://cdn.pixabay.com/video/...">
  </div>
  <div class="form-group">
    <label>Music Playlist (one URL per line — MP3, YouTube, SoundCloud, or FMA album link)</label>
    <textarea name="fallback_playlist" id="fallback_playlist" rows="3" placeholder="https://files.freemusicarchive.org/..."></textarea>
  </div>
  <div style="display:flex;gap:8px;align-items:center">
    <input type="url" id="fmaUrl" placeholder="https://freemusicarchive.org/music/..." style="flex:1;padding:8px 12px;background:#0d1117;border:1px solid #30363d;border-radius:6px;color:#c9d1d9;font-size:13px">
    <button class="btn btn-grey btn-sm" onclick="fetchFMAtracks()">Fetch from FMA</button>
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
      document.getElementById('fallback_playlist').value = d.tracks.join('\n');
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

if __name__ == '__main__':
    init_wanted()
    app.run(host='0.0.0.0', port=8080, debug=False)
