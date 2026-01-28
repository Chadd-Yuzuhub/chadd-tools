#!/usr/bin/env python3
"""Bluesky Auto-Poster — checks queue for approved posts/replies and publishes them.

Runs via crontab every 10 minutes. Self-contained, no session tokens needed.
Respects: max 1 standalone post/day, no posting 23:00-08:00, replies anytime (during waking hours).
Notifies via Clawdbot webhook after each post.
"""

import json
import os
import sys
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Config
DASHBOARD_URL = "http://localhost:8790"
DASHBOARD_PIN = "yuzu2026"
STATE_FILE = Path(__file__).parent / "autoposter-state.json"
ENV_FILE = Path.home() / ".chadd-mail.env"
BERLIN = timezone(timedelta(hours=1))  # CET (simplified, no DST handling)

def load_env():
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"last_post_date": None, "posts_today": 0}

def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))

def is_quiet_hours():
    now = datetime.now(BERLIN)
    return now.hour >= 23 or now.hour < 8

def get_next_approved():
    """Get next approved post from dashboard API."""
    try:
        r = requests.get(f"{DASHBOARD_URL}/api/next", params={"token": DASHBOARD_PIN}, timeout=5)
        if r.status_code == 200:
            data = r.json()
            return data if data else None
    except Exception as e:
        print(f"Dashboard unreachable: {e}")
    return None

def mark_posted(post_id, post_uri=None):
    """Mark post as posted in dashboard."""
    try:
        params = {"token": DASHBOARD_PIN}
        if post_uri:
            params["post_uri"] = post_uri
        requests.post(f"{DASHBOARD_URL}/api/mark-posted/{post_id}", params=params, timeout=5)
    except Exception as e:
        print(f"Failed to mark posted: {e}")

def publish_post(env, post):
    """Publish a post or reply to Bluesky."""
    from atproto import Client

    client = Client()
    client.login(env['BSKY_HANDLE'], env['BSKY_PASS'])

    text = post['text']
    post_type = post.get('type', 'post')
    reply_to = post.get('reply_to')

    if post_type == 'reply' and reply_to and reply_to.get('uri') and reply_to.get('cid'):
        # Fetch parent post to get root reference
        from atproto import models
        parent_uri = reply_to['uri']
        parent_cid = reply_to['cid']

        # Get the parent post to check if it's itself a reply (need root ref)
        try:
            thread = client.get_post_thread(uri=parent_uri, depth=0)
            parent_post = thread.thread.post
            # If parent is a reply, use its root; otherwise parent IS the root
            if hasattr(parent_post, 'record') and hasattr(parent_post.record, 'reply') and parent_post.record.reply:
                root_uri = parent_post.record.reply.root.uri
                root_cid = parent_post.record.reply.root.cid
            else:
                root_uri = parent_uri
                root_cid = parent_cid
        except:
            root_uri = parent_uri
            root_cid = parent_cid

        reply_ref = models.AppBskyFeedPost.ReplyRef(
            parent=models.create_strong_ref(parent_uri, parent_cid),
            root=models.create_strong_ref(root_uri, root_cid),
        )
        result = client.send_post(text=text, reply_to=reply_ref)
    else:
        result = client.send_post(text=text)

    return result.uri

def notify_stefan(env, post, post_uri):
    """Send notification via Clawdbot webhook (optional)."""
    post_type = post.get('type', 'post')
    reply_to = post.get('reply_to', {})

    if post_type == 'reply':
        msg = f"↩ Reply gepostet auf @{reply_to.get('author_handle', '?')}:\n\n\"{post['text'][:200]}\""
    else:
        msg = f"📤 Bluesky Post veröffentlicht:\n\n\"{post['text'][:200]}\""

    rkey = post_uri.split('/')[-1] if post_uri else ''
    if rkey:
        msg += f"\n\nhttps://bsky.app/profile/chadd-yuzu.bsky.social/post/{rkey}"

    # Try to notify via local Clawdbot API
    try:
        r = requests.post("http://localhost:3377/api/notify", json={"message": msg}, timeout=5)
        if r.status_code == 200:
            return
    except:
        pass

    # Fallback: write to a notification file that heartbeat can pick up
    notif_file = Path(__file__).parent / "pending-notification.txt"
    notif_file.write_text(msg)
    print(f"Notification saved to {notif_file}")

def main():
    if is_quiet_hours():
        return

    env = load_env()
    if 'BSKY_HANDLE' not in env:
        print("Missing BSKY credentials")
        sys.exit(1)

    post = get_next_approved()
    if not post:
        return

    state = load_state()
    today = datetime.now(BERLIN).strftime("%Y-%m-%d")
    post_type = post.get('type', 'post')

    # Reset daily counter if new day
    if state.get('last_post_date') != today:
        state['posts_today'] = 0
        state['last_post_date'] = today

    # Standalone posts: max 1 per day. Replies: unlimited.
    if post_type != 'reply' and state['posts_today'] >= 1:
        print(f"Already posted {state['posts_today']} standalone post(s) today, skipping.")
        return

    try:
        post_uri = publish_post(env, post)
        print(f"Published: {post_uri}")

        mark_posted(post['id'], post_uri)

        if post_type != 'reply':
            state['posts_today'] += 1
        save_state(state)

        notify_stefan(env, post, post_uri)

    except Exception as e:
        print(f"Publish failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
