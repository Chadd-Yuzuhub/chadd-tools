#!/usr/bin/env python3
"""Uptime checker for websites. Checks HTTP status, response time, SSL cert expiry."""

import json
import os
import socket
import ssl
import sys
import time
from datetime import datetime, timezone
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

SITES = [
    "https://yuzu.chat",
    "https://yuzuhub.com",
    "https://voltplan.app",
]

STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "memory", "uptime-state.json")

def check_ssl(hostname):
    """Check SSL certificate expiry."""
    try:
        ctx = ssl.create_default_context()
        with ctx.wrap_socket(socket.socket(), server_hostname=hostname) as s:
            s.settimeout(10)
            s.connect((hostname, 443))
            cert = s.getpeercert()
            expires = datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
            days_left = (expires - datetime.now(timezone.utc)).days
            return {"valid": True, "expires": expires.isoformat(), "days_left": days_left}
    except Exception as e:
        return {"valid": False, "error": str(e)}

def check_site(url):
    """Check a single site for availability."""
    result = {
        "url": url,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ok": False,
    }
    
    hostname = url.replace("https://", "").replace("http://", "").split("/")[0]
    
    # HTTP check
    try:
        req = Request(url, headers={"User-Agent": "Chadd-Uptime/1.0"})
        start = time.time()
        resp = urlopen(req, timeout=15)
        elapsed = round((time.time() - start) * 1000)
        result["status"] = resp.status
        result["response_ms"] = elapsed
        result["ok"] = 200 <= resp.status < 400
    except HTTPError as e:
        result["status"] = e.code
        result["error"] = str(e)
    except URLError as e:
        result["error"] = str(e.reason)
    except Exception as e:
        result["error"] = str(e)
    
    # SSL check
    if url.startswith("https://"):
        result["ssl"] = check_ssl(hostname)
    
    return result

def load_state():
    """Load previous state."""
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_state(state):
    """Save current state."""
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def main():
    results = []
    alerts = []
    state = load_state()
    
    for url in SITES:
        r = check_site(url)
        results.append(r)
        
        prev = state.get(url, {})
        was_ok = prev.get("ok", True)
        
        # Site went down
        if not r["ok"] and was_ok:
            alerts.append(f"🔴 {url} ist DOWN! {r.get('error', f'Status {r.get('status', '?')}')}")
        
        # Site came back up
        if r["ok"] and not was_ok:
            alerts.append(f"🟢 {url} ist wieder UP! ({r['response_ms']}ms)")
        
        # SSL expiring soon (< 14 days)
        ssl_info = r.get("ssl", {})
        if ssl_info.get("valid") and ssl_info.get("days_left", 999) < 14:
            alerts.append(f"⚠️ {url} SSL-Zertifikat läuft in {ssl_info['days_left']} Tagen ab!")
        
        # SSL broken
        if ssl_info and not ssl_info.get("valid"):
            alerts.append(f"🔴 {url} SSL-Fehler: {ssl_info.get('error', 'unbekannt')}")
        
        # Slow response (> 5s)
        if r.get("response_ms", 0) > 5000:
            alerts.append(f"🐌 {url} antwortet langsam: {r['response_ms']}ms")
        
        # Update state
        state[url] = {"ok": r["ok"], "last_check": r["timestamp"]}
    
    save_state(state)
    
    # Output
    if "--json" in sys.argv:
        print(json.dumps(results, indent=2))
    elif "--quiet" in sys.argv:
        # Only output if there are alerts
        if alerts:
            for a in alerts:
                print(a)
    else:
        for r in results:
            status = "✅" if r["ok"] else "❌"
            ms = f"{r.get('response_ms', '?')}ms" if r.get("response_ms") else "timeout"
            ssl_info = r.get("ssl", {})
            ssl_str = f"SSL {ssl_info.get('days_left', '?')}d" if ssl_info.get("valid") else "SSL ⚠️" if ssl_info else ""
            print(f"{status} {r['url']} — {r.get('status', 'ERR')} {ms} {ssl_str}")
        
        if alerts:
            print("\n--- Alerts ---")
            for a in alerts:
                print(a)

if __name__ == "__main__":
    main()
