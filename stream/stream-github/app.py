#!/usr/bin/env python3
"""
stream-github — Flask control panel for multi-platform restreaming via GitHub Actions.

Triggers workflow_dispatch on a GitHub repo to start/stop restreams.
Each platform (Twitch, YouTube, TikTok, Kick, Facebook) can be started/stopped independently.
"""

import os
import json
import hashlib
import hmac
import time
from functools import wraps
from pathlib import Path

import requests
from dotenv import load_dotenv
from flask import (
    Flask, request, jsonify, session, redirect, url_for, render_template_string
)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-change-me')

PANEL_PASSWORD = os.environ.get('PANEL_PASSWORD', 'admin')
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
GITHUB_OWNER = os.environ.get('GITHUB_OWNER', '')
GITHUB_REPO = os.environ.get('GITHUB_REPO', '')
WORKFLOW_FILE = os.environ.get('WORKFLOW_FILE', 'restream.yml')
TIKTOK_24H_WORKFLOW = os.environ.get('TIKTOK_24H_WORKFLOW', 'tiktok-24h.yml')

PLATFORMS_FILE = Path(__file__).parent / 'platforms.json'

DEFAULT_PLATFORMS = [
    {'name': 'Twitch', 'rtmp_url': 'rtmp://live.twitch.tv/app/', 'stream_key': '', 'enabled': True, 'status': 'idle'},
    {'name': 'YouTube', 'rtmp_url': 'rtmp://a.rtmp.youtube.com/live2/', 'stream_key': '', 'enabled': True, 'status': 'idle'},
    {'name': 'TikTok', 'rtmp_url': '', 'stream_key': '', 'enabled': True, 'status': 'idle'},
    {'name': 'Kick', 'rtmp_url': 'rtmp://push.kick.com/live/', 'stream_key': '', 'enabled': True, 'status': 'idle'},
    {'name': 'Facebook', 'rtmp_url': 'rtmps://live-api-s.facebook.com:443/rtmp/', 'stream_key': '', 'enabled': True, 'status': 'idle'},
]


def load_platforms():
    if PLATFORMS_FILE.exists():
        with open(PLATFORMS_FILE) as f:
            return json.load(f)
    save_platforms(DEFAULT_PLATFORMS)
    return DEFAULT_PLATFORMS


def save_platforms(platforms):
    with open(PLATFORMS_FILE, 'w') as f:
        json.dump(platforms, f, indent=2)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('authenticated'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def github_dispatch(workflow_id, inputs):
    if not GITHUB_TOKEN or not GITHUB_OWNER or not GITHUB_REPO:
        return {'ok': False, 'error': 'GitHub not configured (set GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO)'}
    url = f'https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/workflows/{workflow_id}/dispatches'
    headers = {
        'Authorization': f'Bearer {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
    }
    resp = requests.post(url, json={'ref': 'main', 'inputs': inputs}, headers=headers, timeout=15)
    if resp.status_code in (200, 204):
        return {'ok': True}
    return {'ok': False, 'error': f'GitHub API {resp.status_code}: {resp.text[:200]}'}


# --- Auth ---

LOGIN_HTML = '''<!DOCTYPE html><html><head><title>Stream Panel - Login</title>
<style>
body{background:#0a0a0a;color:#fff;font-family:system-ui;display:flex;justify-content:center;align-items:center;height:100vh;margin:0}
.login-box{background:#111;padding:40px;border-radius:12px;width:340px;box-shadow:0 0 30px rgba(139,92,246,.15)}
h1{text-align:center;font-size:1.4rem;margin-bottom:8px}
p{text-align:center;color:#888;font-size:.85rem;margin-bottom:24px}
input{width:100%;padding:12px;border:1px solid #333;border-radius:8px;background:#1a1a2e;color:#fff;font-size:1rem;margin-bottom:16px;box-sizing:border-box}
button{width:100%;padding:12px;background:#7c3aed;color:#fff;border:none;border-radius:8px;font-size:1rem;cursor:pointer;font-weight:600}
button:hover{background:#6d28d9}
.err{color:#ef4444;text-align:center;margin-bottom:12px;font-size:.85rem}
</style></head><body>
<div class="login-box">
<h1>Stream Panel</h1><p>Enter password to continue</p>
{% if error %}<div class="err">{{ error }}</div>{% endif %}
<form method="POST"><input name="password" type="password" placeholder="Password" autofocus>
<button type="submit">Login</button></form></div></body></html>'''


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        if request.form.get('password') == PANEL_PASSWORD:
            session['authenticated'] = True
            return redirect(url_for('dashboard'))
        error = 'Wrong password'
    return render_template_string(LOGIN_HTML, error=error)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# --- Dashboard ---

DASHBOARD_HTML = '''<!DOCTYPE html><html><head><title>Stream Panel</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0a0a0a;color:#fff;font-family:system-ui}
.header{background:#111;padding:16px 24px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #222}
.header h1{font-size:1.2rem}.header a{color:#888;text-decoration:none;font-size:.85rem}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:20px;padding:24px;max-width:1200px;margin:0 auto}
.card{background:#111;border-radius:12px;padding:20px;border:1px solid #222}
.card h2{font-size:1.1rem;margin-bottom:12px;display:flex;align-items:center;gap:8px}
.status{display:inline-block;width:10px;height:10px;border-radius:50%}
.status.idle{background:#666}.status.running{background:#22c55e}
.card label{font-size:.75rem;color:#888;display:block;margin-bottom:4px;margin-top:12px}
.card input,.card select{width:100%;padding:8px;border:1px solid #333;border-radius:6px;background:#1a1a2e;color:#fff;font-size:.85rem;box-sizing:border-box}
.card .toggle{display:flex;align-items:center;gap:8px;margin-top:12px}
.card .toggle input[type=checkbox]{width:18px;height:18px}
.btn{padding:10px 20px;border:none;border-radius:8px;font-size:.85rem;cursor:pointer;font-weight:600;margin-top:12px}
.btn-start{background:#22c55e;color:#000}.btn-start:hover{background:#16a34a}
.btn-stop{background:#ef4444;color:#fff}.btn-stop:hover{background:#dc2626}
.btn-save{background:#7c3aed;color:#fff;width:100%}.btn-save:hover{background:#6d28d9}
.msg{text-align:center;padding:16px;color:#888;font-size:.85rem}
.status-bar{background:#111;padding:12px 24px;border-top:1px solid #222;text-align:center;color:#666;font-size:.8rem}
</style></head><body>
<div class="header"><h1>Stream Panel</h1><a href="/logout">Logout</a></div>
<div class="grid" id="platforms"></div>
<div class="status-bar" id="statusbar">Loading...</div>
<script>
async function load(){
  const r=await fetch('/api/platforms');const d=await r.json();const g=document.getElementById('platforms');g.innerHTML='';
  d.platforms.forEach((p,i)=>{
    g.innerHTML+=`<div class="card"><h2><span class="status ${p.status}"></span>${p.name}</h2>
    <label>RTMP URL</label><input id="rtmp${i}" value="${p.rtmp_url}">
    <label>Stream Key</label><input id="key${i}" value="${p.stream_key}" type="password">
    <div class="toggle"><input type="checkbox" id="en${i}" ${p.enabled?'checked':''}><label for="en${i}">Enabled</label></div>
    <button class="btn btn-save" onclick="save(${i},'${p.name}')">Save</button>
    <div style="display:flex;gap:8px;margin-top:8px">
    <button class="btn btn-start" onclick="start('${p.name}')">Start</button>
    <button class="btn btn-stop" onclick="stop('${p.name}')">Stop</button>
    </div></div>`;
  });
  const s=await fetch('/api/status');const sd=await s.json();
  document.getElementById('statusbar').textContent=`GitHub: ${sd.github_configured?'Connected':'Not configured'} | Active streams: ${sd.running}/${sd.total}`;
}
async function save(i,name){
  await fetch('/api/platforms',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name,rtmp_url:document.getElementById('rtmp'+i).value,stream_key:document.getElementById('key'+i).value,enabled:document.getElementById('en'+i).checked})});
  load();
}
async function start(name){const r=await fetch('/api/stream/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({platform:name})});const d=await r.json();alert(d.ok?'Stream started: '+name:'Error: '+d.error);load();}
async function stop(name){const r=await fetch('/api/stream/stop',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({platform:name})});const d=await r.json();alert(d.ok?'Stream stopped: '+name:'Error: '+d.error);load();}
load();setInterval(load,10000);
</script></body></html>'''


@app.route('/')
@login_required
def dashboard():
    return render_template_string(DASHBOARD_HTML)


# --- API ---

@app.route('/api/platforms', methods=['GET'])
@login_required
def api_list_platforms():
    return jsonify({'platforms': load_platforms()})


@app.route('/api/platforms', methods=['POST'])
@login_required
def api_save_platform():
    data = request.get_json(force=True)
    platforms = load_platforms()
    for p in platforms:
        if p['name'].lower() == data.get('name', '').lower():
            if 'rtmp_url' in data:
                p['rtmp_url'] = data['rtmp_url']
            if 'stream_key' in data:
                p['stream_key'] = data['stream_key']
            if 'enabled' in data:
                p['enabled'] = data['enabled']
            break
    save_platforms(platforms)
    return jsonify({'ok': True})


@app.route('/api/stream/start', methods=['POST'])
@login_required
def api_start_stream():
    data = request.get_json(force=True)
    platform_name = data.get('platform', '')
    platforms = load_platforms()
    target = next((p for p in platforms if p['name'].lower() == platform_name.lower()), None)
    if not target:
        return jsonify({'ok': False, 'error': f'Platform not found: {platform_name}'}), 404
    if not target.get('stream_key'):
        return jsonify({'ok': False, 'error': f'No stream key configured for {platform_name}'}), 400

    result = github_dispatch(WORKFLOW_FILE, {
        'platform': platform_name,
        'action': 'start',
        'rtmp_url': target.get('rtmp_url', ''),
        'stream_key': target.get('stream_key', ''),
    })
    if result['ok']:
        target['status'] = 'running'
        save_platforms(platforms)
    return jsonify(result)


@app.route('/api/stream/stop', methods=['POST'])
@login_required
def api_stop_stream():
    data = request.get_json(force=True)
    platform_name = data.get('platform', '')
    platforms = load_platforms()
    target = next((p for p in platforms if p['name'].lower() == platform_name.lower()), None)
    if not target:
        return jsonify({'ok': False, 'error': f'Platform not found: {platform_name}'}), 404

    result = github_dispatch(WORKFLOW_FILE, {
        'platform': platform_name,
        'action': 'stop',
        'rtmp_url': '',
        'stream_key': '',
    })
    if result['ok']:
        target['status'] = 'idle'
        save_platforms(platforms)
    return jsonify(result)


@app.route('/api/status')
@login_required
def api_status():
    platforms = load_platforms()
    running = sum(1 for p in platforms if p.get('status') == 'running')
    return jsonify({
        'ok': True,
        'running': running,
        'total': len(platforms),
        'github_configured': bool(GITHUB_TOKEN and GITHUB_OWNER and GITHUB_REPO),
    })


@app.route('/api/health')
def health():
    return jsonify({'ok': True, 'status': 'running'})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f'Stream Panel running on http://0.0.0.0:{port}')
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('FLASK_DEBUG', '0') == '1')
