from flask import Flask, request, jsonify
import os, time, json, requests, threading

app = Flask(__name__)

GITHUB_TOKEN = ''
GITHUB_REPO = ''
GITHUB_OWNER = ''
current_run_id = None
config_path = 'gh_config.json'
log_buffer = []
log_lock = threading.Lock()

DEFAULTS = {
    'source_url': 'https://www.twitch.tv/inoxtag',
    'output_url': '',
    'twitch_key': '',
    'backup_list': '',
    'bitrate': '192k',
    'github_token': '',
    'github_owner': '',
    'github_repo': '',
    'keepalive': False,
}

wanted = False  # user wants stream to stay on

def load_config():
    try:
        with open(config_path) as f:
            return json.load(f)
    except:
        return dict(DEFAULTS)

def save_config(cfg):
    with open(config_path, 'w') as f:
        json.dump(cfg, f)

def log(msg):
    with log_lock:
        ts = time.strftime('%H:%M:%S')
        log_buffer.append(f'[{ts}] {msg}')
        if len(log_buffer) > 200:
            log_buffer[:] = log_buffer[-200:]

def trigger_workflow(source_url, output_url, twitch_key=''):
    cfg = load_config()
    token = cfg.get('github_token') or GITHUB_TOKEN
    owner = cfg.get('github_owner') or GITHUB_OWNER
    repo = cfg.get('github_repo') or GITHUB_REPO
    if not token or not owner or not repo:
        return None, 'Missing GitHub config'
    url = f'https://api.github.com/repos/{owner}/{repo}/actions/workflows/restream.yml/dispatches'
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github.v3+json'}
    inputs = {'source_url': source_url}
    if output_url:
        inputs['output_url'] = output_url
    if twitch_key:
        inputs['twitch_key'] = twitch_key
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
                        log('Keepalive: re-triggering workflow')
                        trigger_workflow(cfg['source_url'], cfg.get('output_url',''), cfg.get('twitch_key',''))
            elif not wanted:
                time.sleep(30)
                continue
        except Exception as e:
            log(f'Keepalive error: {e}')
        time.sleep(60)

threading.Thread(target=keepalive_loop, daemon=True).start()

@app.route('/')
def index():
    return HTML_PANEL

@app.route('/config', methods=['POST'])
def update_config():
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
    if not cfg.get('source_url') or not (cfg.get('output_url') or cfg.get('twitch_key')):
        return jsonify({'ok': False, 'error': 'Missing source URL, and no output or Twitch key configured'})
    msg, err = trigger_workflow(cfg['source_url'], cfg.get('output_url',''), cfg.get('twitch_key',''))
    if err:
        return jsonify({'ok': False, 'error': err})
    wanted = True
    log('Workflow triggered')
    return jsonify({'ok': True, 'msg': msg})

@app.route('/start_twitch')
def start_twitch():
    global wanted
    cfg = load_config()
    if not cfg.get('source_url') or not cfg.get('twitch_key'):
        return jsonify({'ok': False, 'error': 'Missing source URL or Twitch key'})
    msg, err = trigger_workflow(cfg['source_url'], '', cfg.get('twitch_key',''))
    if err:
        return jsonify({'ok': False, 'error': err})
    wanted = True
    log('Twitch-only workflow triggered')
    return jsonify({'ok': True, 'msg': msg})

@app.route('/stop')
def stop_stream():
    global wanted
    wanted = False
    cfg = load_config()
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

@app.route('/resolve')
def resolve_source():
    cfg = load_config()
    if not cfg.get('source_url'):
        return jsonify({'ok': False, 'error': 'No source URL'}), 400
    import subprocess
    base = ['yt-dlp', '--socket-timeout', '15']
    for fmt in [['--format', 'best'], ['--format', 'worst']]:
        try:
            r = subprocess.run(base + fmt + ['-g', cfg['source_url']],
                capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                lines = [l.strip() for l in r.stdout.strip().split('\n') if l.strip()]
                if lines:
                    return jsonify({'ok': True, 'hls': lines[-1], 'source': cfg['source_url']})
        except:
            pass
    return jsonify({'ok': False, 'error': 'Not live'}), 400

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
    <label>Output URL (Kick/Custom)</label>
    <input type="text" name="output_url" id="output_url" placeholder="srt://... or rtmp://...">
    <label style="margin-top:8px">Twitch Stream Key</label>
    <input type="text" name="twitch_key" id="twitch_key" placeholder="live_xxxxxxxxx_xxxxxxxxxxxxxxxxxx">
  </div>
    <div class="form-group" style="margin-top:4px">
      <label style="display:flex;align-items:center;gap:8px">
        <input type="checkbox" name="keepalive" id="keepalive" onchange="saveConfig()" style="width:auto">
        Keep Alive (auto-restart after 6h)
      </label>
    </div>
    <div class="actions">
      <button class="btn btn-green" id="btnGoLive" onclick="goLive()">▶ Go Live (All)</button>
      <button class="btn btn-purple" id="btnGoTwitch" onclick="goTwitch()">▶ Go Live (Twitch)</button>
      <button class="btn btn-red" id="btnStop" onclick="stopStream()" disabled>⏹ Stop</button>
      <button class="btn btn-blue btn-sm" onclick="saveConfig()">💾 Save</button>
      <button class="btn btn-grey btn-sm" onclick="testSource()">🔍 Test Source</button>
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
  fetch('/resolve').then(r=>r.json()).then(d=>{
    el.textContent = d.ok ? '✓ Live — HLS resolved' : '✗ Not live';
  }).catch(()=>el.textContent='✗ Failed');
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
function goTwitch() {
  document.getElementById('btnGoTwitch').disabled = true;
  addLog('Starting Twitch only...','info');
  saveConfig(() => {
    fetch('/start_twitch').then(r=>r.json()).then(d=>{
      if(!d.ok) { addLog('Error: '+d.error,'err'); document.getElementById('btnGoTwitch').disabled = false; }
    }).catch(e=>{ addLog('Start failed','err'); document.getElementById('btnGoTwitch').disabled = false; });
  });
}
function stopStream() {
  document.getElementById('btnStop').disabled = true;
  addLog('Stopping...','warn');
  fetch('/stop').then(r=>r.json()).then(d=>{
    addLog(d.ok ? 'Stopped' : 'Error: '+d.error, d.ok ? 'warn' : 'err');
  }).catch(e=>addLog('Stop failed','err'));
}
function addLog(msg,cls='info') {
  const box = document.getElementById('logBox');
  box.innerHTML += '<span class="'+cls+'">['+new Date().toLocaleTimeString()+'] '+msg+'</span>\n';
  box.scrollTop = box.scrollHeight;
}
function updateStatus() {
  fetch('/status').then(r=>r.json()).then(d=>{
    const dot = document.getElementById('statusDot');
    const txt = document.getElementById('statusText');
    if(d.live) {
      dot.className = 'status-dot live';
      txt.textContent = '● LIVE' + (d.keepalive ? ' (auto-restart)' : '');
      document.getElementById('btnGoLive').disabled = true;
      document.getElementById('btnGoTwitch').disabled = true;
      document.getElementById('btnStop').disabled = false;
    } else {
      dot.className = 'status-dot stopped';
      txt.textContent = '○ Stopped';
      document.getElementById('btnGoLive').disabled = false;
      document.getElementById('btnGoTwitch').disabled = false;
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)
