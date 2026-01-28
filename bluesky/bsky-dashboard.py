#!/usr/bin/env python3
"""Bluesky Post Dashboard — Approve/reject/manage posts before they go live."""

import json
import os
import uuid
import secrets
from datetime import datetime
from pathlib import Path
from functools import wraps
from flask import Flask, request, jsonify, render_template_string, redirect, url_for, session

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

QUEUE_FILE = Path(__file__).parent / "bsky-queue.json"
ENV_FILE = Path.home() / ".chadd-mail.env"

# Simple password auth
DASHBOARD_PIN = None

def load_env():
    """Load env vars from ~/.chadd-mail.env"""
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env

def get_pin():
    global DASHBOARD_PIN
    if DASHBOARD_PIN is None:
        env = load_env()
        DASHBOARD_PIN = env.get("BSKY_DASHBOARD_PIN", "yuzu2026")
    return DASHBOARD_PIN

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            if request.is_json:
                return jsonify({"error": "unauthorized"}), 401
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def load_queue():
    if QUEUE_FILE.exists():
        return json.loads(QUEUE_FILE.read_text())
    return {"posts": []}

def save_queue(data):
    QUEUE_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))

# ─── Templates ───

LOGIN_HTML = """
<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>🍋 Chadd Bluesky Dashboard</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
         background: #0f1419; color: #e7e9ea; display: flex; align-items: center;
         justify-content: center; min-height: 100vh; }
  .login-box { background: #16202a; border: 1px solid #2f3336; border-radius: 16px;
               padding: 40px; width: 340px; text-align: center; }
  .login-box h1 { font-size: 24px; margin-bottom: 8px; }
  .login-box p { color: #71767b; margin-bottom: 24px; font-size: 14px; }
  input[type=password] { width: 100%; padding: 12px 16px; border-radius: 8px;
                         border: 1px solid #2f3336; background: #0f1419; color: #e7e9ea;
                         font-size: 16px; margin-bottom: 16px; outline: none; }
  input[type=password]:focus { border-color: #1d9bf0; }
  button { width: 100%; padding: 12px; border-radius: 24px; border: none;
           background: #1d9bf0; color: white; font-size: 16px; font-weight: 700;
           cursor: pointer; }
  button:hover { background: #1a8cd8; }
  .error { color: #f4212e; font-size: 13px; margin-bottom: 12px; }
</style>
</head>
<body>
<div class="login-box">
  <h1>🍋 Chadd</h1>
  <p>Bluesky Post Dashboard</p>
  {% if error %}<div class="error">{{ error }}</div>{% endif %}
  <form method="post">
    <input type="password" name="pin" placeholder="PIN" autofocus>
    <button type="submit">Login</button>
  </form>
</div>
</body>
</html>
"""

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>🍋 Chadd — Bluesky Posts</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
         background: #0f1419; color: #e7e9ea; padding: 16px; max-width: 640px; margin: 0 auto; }
  header { display: flex; align-items: center; justify-content: space-between;
           padding: 16px 0; border-bottom: 1px solid #2f3336; margin-bottom: 20px; }
  header h1 { font-size: 20px; }
  header a { color: #71767b; text-decoration: none; font-size: 13px; }
  .tabs { display: flex; gap: 0; margin-bottom: 20px; border-bottom: 1px solid #2f3336; }
  .tab { padding: 12px 20px; color: #71767b; text-decoration: none; font-size: 14px;
         font-weight: 600; border-bottom: 2px solid transparent; }
  .tab.active { color: #e7e9ea; border-bottom-color: #1d9bf0; }
  .tab:hover { background: rgba(231,233,234,0.05); }
  .post-card { background: #16202a; border: 1px solid #2f3336; border-radius: 12px;
               padding: 16px; margin-bottom: 12px; }
  .post-text { font-size: 15px; line-height: 1.5; white-space: pre-wrap; margin-bottom: 12px; }
  .post-meta { font-size: 12px; color: #71767b; margin-bottom: 12px; }
  .post-actions { display: flex; gap: 8px; }
  .btn { padding: 8px 20px; border-radius: 20px; border: none; font-size: 14px;
         font-weight: 700; cursor: pointer; text-decoration: none; display: inline-block; }
  .btn-approve { background: #00ba7c; color: white; }
  .btn-approve:hover { background: #00a06a; }
  .btn-reject { background: transparent; color: #f4212e; border: 1px solid #67070f; }
  .btn-reject:hover { background: rgba(244,33,46,0.1); }
  .btn-edit { background: transparent; color: #1d9bf0; border: 1px solid #1d4e7a; }
  .btn-edit:hover { background: rgba(29,155,240,0.1); }
  .btn-delete { background: transparent; color: #71767b; border: 1px solid #2f3336; }
  .btn-delete:hover { background: rgba(231,233,234,0.05); }
  .badge { display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 12px;
           font-weight: 600; margin-bottom: 8px; }
  .badge-pending { background: #1d4e7a; color: #1d9bf0; }
  .badge-approved { background: #0d3c26; color: #00ba7c; }
  .badge-rejected { background: #67070f; color: #f4212e; }
  .badge-posted { background: #2f3336; color: #71767b; }
  .empty { text-align: center; color: #71767b; padding: 40px; font-size: 15px; }
  .compose { background: #16202a; border: 1px solid #2f3336; border-radius: 12px;
             padding: 16px; margin-bottom: 20px; }
  textarea { width: 100%; padding: 12px; border-radius: 8px; border: 1px solid #2f3336;
             background: #0f1419; color: #e7e9ea; font-size: 15px; font-family: inherit;
             resize: vertical; min-height: 80px; outline: none; }
  textarea:focus { border-color: #1d9bf0; }
  .compose-actions { display: flex; justify-content: space-between; align-items: center; margin-top: 12px; }
  .char-count { font-size: 13px; color: #71767b; }
  .char-count.warn { color: #ffad1f; }
  .char-count.over { color: #f4212e; }
  .edit-form textarea { margin-bottom: 8px; }
  .edit-form { display: none; }
  .edit-form.active { display: block; }
  .post-text-display { cursor: default; }
  .status-msg { padding: 12px 16px; border-radius: 8px; margin-bottom: 16px; font-size: 14px; }
  .status-success { background: #0d3c26; color: #00ba7c; border: 1px solid #00ba7c33; }
</style>
</head>
<body>
<header>
  <h1>🍋 Bluesky Posts</h1>
  <a href="/logout">Logout</a>
</header>

{% if status_msg %}
<div class="status-msg status-success">{{ status_msg }}</div>
{% endif %}

<div class="compose">
  <form method="post" action="/add">
    <textarea name="text" placeholder="Neuen Post schreiben…" maxlength="300"
              oninput="updateCount(this)"></textarea>
    <div class="compose-actions">
      <span class="char-count" id="charCount">0 / 300</span>
      <button type="submit" class="btn btn-approve">+ Hinzufügen</button>
    </div>
  </form>
</div>

<div class="tabs">
  <a class="tab {% if tab == 'pending' %}active{% endif %}" href="/?tab=pending">
    Pending{% if counts.pending %} ({{ counts.pending }}){% endif %}</a>
  <a class="tab {% if tab == 'approved' %}active{% endif %}" href="/?tab=approved">
    Approved{% if counts.approved %} ({{ counts.approved }}){% endif %}</a>
  <a class="tab {% if tab == 'posted' %}active{% endif %}" href="/?tab=posted">
    Posted{% if counts.posted %} ({{ counts.posted }}){% endif %}</a>
  <a class="tab {% if tab == 'rejected' %}active{% endif %}" href="/?tab=rejected">
    Rejected{% if counts.rejected %} ({{ counts.rejected }}){% endif %}</a>
</div>

{% if not filtered_posts %}
<div class="empty">
  {% if tab == 'pending' %}Keine Posts zur Freigabe.
  {% elif tab == 'approved' %}Keine freigegebenen Posts in der Warteschlange.
  {% elif tab == 'posted' %}Noch keine Posts veröffentlicht.
  {% else %}Keine abgelehnten Posts.{% endif %}
</div>
{% endif %}

{% for post in filtered_posts %}
<div class="post-card" id="post-{{ post.id }}">
  <span class="badge badge-{{ post.status }}">{{ post.status | upper }}</span>
  <div class="post-text post-text-display" id="text-{{ post.id }}">{{ post.text }}</div>

  <div class="edit-form" id="edit-{{ post.id }}">
    <form method="post" action="/edit/{{ post.id }}">
      <textarea name="text" maxlength="300">{{ post.text }}</textarea>
      <div class="post-actions">
        <button type="submit" class="btn btn-approve">Speichern</button>
        <button type="button" class="btn btn-delete" onclick="toggleEdit('{{ post.id }}')">Abbrechen</button>
      </div>
    </form>
  </div>

  <div class="post-meta">
    Erstellt: {{ post.created_at[:16] }}
    {% if post.approved_at %} · Freigegeben: {{ post.approved_at[:16] }}{% endif %}
    {% if post.posted_at %} · Gepostet: {{ post.posted_at[:16] }}{% endif %}
    {% if post.post_uri %} · <a href="https://bsky.app/profile/chadd-yuzu.bsky.social/post/{{ post.post_uri.split('/')[-1] }}" target="_blank" style="color:#1d9bf0">Ansehen ↗</a>{% endif %}
    · {{ post.text | length }} Zeichen
  </div>

  <div class="post-actions" id="actions-{{ post.id }}">
    {% if post.status == 'pending' %}
      <form method="post" action="/approve/{{ post.id }}" style="display:inline">
        <button type="submit" class="btn btn-approve">✓ Freigeben</button>
      </form>
      <form method="post" action="/reject/{{ post.id }}" style="display:inline">
        <button type="submit" class="btn btn-reject">✗ Ablehnen</button>
      </form>
      <button class="btn btn-edit" onclick="toggleEdit('{{ post.id }}')">Bearbeiten</button>
    {% elif post.status == 'approved' %}
      <form method="post" action="/reject/{{ post.id }}" style="display:inline">
        <button type="submit" class="btn btn-reject">Zurückziehen</button>
      </form>
      <button class="btn btn-edit" onclick="toggleEdit('{{ post.id }}')">Bearbeiten</button>
    {% elif post.status == 'rejected' %}
      <form method="post" action="/approve/{{ post.id }}" style="display:inline">
        <button type="submit" class="btn btn-approve">Doch freigeben</button>
      </form>
      <form method="post" action="/delete/{{ post.id }}" style="display:inline">
        <button type="submit" class="btn btn-delete">Löschen</button>
      </form>
    {% endif %}
  </div>
</div>
{% endfor %}

<script>
function updateCount(el) {
  const c = el.value.length;
  const span = document.getElementById('charCount');
  span.textContent = c + ' / 300';
  span.className = 'char-count' + (c > 300 ? ' over' : c > 250 ? ' warn' : '');
}
function toggleEdit(id) {
  const form = document.getElementById('edit-' + id);
  form.classList.toggle('active');
}
</script>
</body>
</html>
"""

# ─── Routes ───

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("pin") == get_pin():
            session["authenticated"] = True
            return redirect(url_for("dashboard"))
        error = "Falscher PIN"
    return render_template_string(LOGIN_HTML, error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
@login_required
def dashboard():
    data = load_queue()
    tab = request.args.get("tab", "pending")
    status_msg = request.args.get("msg")
    
    counts = {}
    for s in ["pending", "approved", "posted", "rejected"]:
        counts[s] = sum(1 for p in data["posts"] if p["status"] == s)
    
    filtered = [p for p in data["posts"] if p["status"] == tab]
    # Sort: newest first
    filtered.sort(key=lambda p: p.get("created_at", ""), reverse=True)
    
    return render_template_string(DASHBOARD_HTML,
        posts=data["posts"], filtered_posts=filtered, tab=tab,
        counts=counts, status_msg=status_msg)

@app.route("/add", methods=["POST"])
@login_required
def add_post():
    text = request.form.get("text", "").strip()
    if not text:
        return redirect(url_for("dashboard"))
    
    data = load_queue()
    post = {
        "id": uuid.uuid4().hex[:8],
        "text": text,
        "status": "pending",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "approved_at": None,
        "posted_at": None,
        "post_uri": None,
    }
    data["posts"].append(post)
    save_queue(data)
    return redirect(url_for("dashboard", msg="Post hinzugefügt", tab="pending"))

@app.route("/approve/<post_id>", methods=["POST"])
@login_required
def approve_post(post_id):
    data = load_queue()
    for p in data["posts"]:
        if p["id"] == post_id:
            p["status"] = "approved"
            p["approved_at"] = datetime.now().isoformat(timespec="seconds")
            break
    save_queue(data)
    return redirect(url_for("dashboard", msg="Post freigegeben ✓", tab="approved"))

@app.route("/reject/<post_id>", methods=["POST"])
@login_required
def reject_post(post_id):
    data = load_queue()
    for p in data["posts"]:
        if p["id"] == post_id:
            p["status"] = "rejected"
            break
    save_queue(data)
    return redirect(url_for("dashboard", msg="Post abgelehnt", tab="rejected"))

@app.route("/edit/<post_id>", methods=["POST"])
@login_required
def edit_post(post_id):
    text = request.form.get("text", "").strip()
    if not text:
        return redirect(url_for("dashboard"))
    data = load_queue()
    for p in data["posts"]:
        if p["id"] == post_id:
            p["text"] = text
            break
    save_queue(data)
    tab = "pending"
    for p in data["posts"]:
        if p["id"] == post_id:
            tab = p["status"]
    return redirect(url_for("dashboard", msg="Post bearbeitet", tab=tab))

@app.route("/delete/<post_id>", methods=["POST"])
@login_required
def delete_post(post_id):
    data = load_queue()
    data["posts"] = [p for p in data["posts"] if p["id"] != post_id]
    save_queue(data)
    return redirect(url_for("dashboard", msg="Post gelöscht"))

# ─── API (for Chadd's scripts) ───

@app.route("/api/next")
def api_next_approved():
    """Get the next approved post (oldest first). Used by posting script."""
    token = request.headers.get("X-Token") or request.args.get("token")
    if token != get_pin():
        return jsonify({"error": "unauthorized"}), 401
    
    data = load_queue()
    approved = [p for p in data["posts"] if p["status"] == "approved"]
    approved.sort(key=lambda p: p.get("created_at", ""))
    
    if approved:
        return jsonify(approved[0])
    return jsonify(None)

@app.route("/api/mark-posted/<post_id>", methods=["POST"])
def api_mark_posted(post_id):
    """Mark a post as posted. Used after successful Bluesky publish."""
    token = request.headers.get("X-Token") or request.args.get("token")
    if token != get_pin():
        return jsonify({"error": "unauthorized"}), 401
    
    post_uri = request.json.get("post_uri") if request.is_json else request.args.get("post_uri")
    
    data = load_queue()
    for p in data["posts"]:
        if p["id"] == post_id:
            p["status"] = "posted"
            p["posted_at"] = datetime.now().isoformat(timespec="seconds")
            if post_uri:
                p["post_uri"] = post_uri
            break
    save_queue(data)
    return jsonify({"ok": True})

@app.route("/api/queue")
def api_queue():
    """Get full queue. Used by Chadd for status checks."""
    token = request.headers.get("X-Token") or request.args.get("token")
    if token != get_pin():
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(load_queue())

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8790)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()
    
    print(f"🍋 Bluesky Dashboard running on http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False)
