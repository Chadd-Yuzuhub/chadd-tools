#!/usr/bin/env python3
"""sipgate AI Flow webhook — Anrufbeantworter für YuzuHub."""
import json
import os
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from threading import Lock

PORT = int(os.environ.get("FLOW_PORT", 8788))
SECRET = os.environ.get("FLOW_SECRET", "")

# Clawdbot hook config for notifications
CLAWDBOT_HOOK_URL = "http://127.0.0.1:18789/hooks/wake"
CLAWDBOT_HOOK_TOKEN = os.environ.get("CLAWDBOT_TOKEN", "d4758672a4163db5f252a0fea602c2c89df93f1670a52d9f")

GREETING = (
    "Hallo, hier ist der Anrufbeantworter von YuzuHub. "
    "Wir sind gerade nicht erreichbar. "
    "Bitte hinterlasse eine Nachricht nach dem Signalton, und wir melden uns bei dir."
)

# Load beep sound (base64 WAV)
BEEP_FILE = os.path.join(os.path.dirname(__file__), "beep.b64")
try:
    with open(BEEP_FILE) as f:
        BEEP_AUDIO = f.read().strip()
except FileNotFoundError:
    BEEP_AUDIO = None

THANKS = "Danke für deine Nachricht. Wir melden uns so bald wie möglich. Tschüss!"

# Store messages per session
sessions = {}
sessions_lock = Lock()


def notify_clawdbot(caller, messages):
    """Notify via Clawdbot hook so Chadd can forward to Stefan/Verena."""
    timestamp = datetime.now().strftime("%H:%M")
    msg_text = "\n".join(f"  > {m}" for m in messages) if messages else "  (keine Nachricht hinterlassen)"
    
    text = (
        f"📞 Anruf auf dem AB\n"
        f"Von: {caller}\n"
        f"Zeit: {timestamp}\n"
        f"Nachricht:\n{msg_text}"
    )
    
    payload = json.dumps({"text": text, "mode": "now"}).encode()
    req = urllib.request.Request(
        CLAWDBOT_HOOK_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {CLAWDBOT_HOOK_TOKEN}"
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            print(f"  Clawdbot notified ({resp.status})", flush=True)
    except Exception as e:
        print(f"  Clawdbot notify failed: {e}", flush=True)


class FlowHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        if SECRET:
            token = self.headers.get("X-API-TOKEN", "")
            if token != SECRET:
                self.send_response(401)
                self.end_headers()
                return

        try:
            event = json.loads(body)
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            return

        event_type = event.get("type", "")
        session_id = event.get("session", {}).get("id", "")
        print(f"[{event_type}] session={session_id[:12]}...", flush=True)

        action = self.handle_event(event)

        if action:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(action).encode())
            text = action.get("text", "")[:80]
            print(f"  → {action.get('type', '?')}: {text}", flush=True)
        else:
            self.send_response(204)
            self.end_headers()

    def handle_event(self, event):
        event_type = event.get("type", "")
        session = event.get("session", {})
        session_id = session.get("id", "")

        if event_type == "session_start":
            caller = session.get("from_phone_number", "unbekannt")
            direction = session.get("direction", "inbound")
            print(f"  📞 Anruf von {caller} ({direction})", flush=True)

            with sessions_lock:
                sessions[session_id] = {
                    "caller": caller,
                    "messages": [],
                    "beeped": False
                }

            return {
                "type": "speak",
                "session_id": session_id,
                "text": GREETING,
                "user_input_timeout_seconds": 30
            }

        elif event_type == "user_speak":
            text = event.get("text", "").strip()
            print(f"  💬 User: {text}", flush=True)

            with sessions_lock:
                if session_id not in sessions:
                    sessions[session_id] = {"caller": "unbekannt", "messages": []}
                if text:
                    sessions[session_id]["messages"].append(text)

            # Return 204 to keep listening (no empty speak)
            return None

        elif event_type == "user_input_timeout":
            # Caller stopped talking — wrap up
            with sessions_lock:
                if session_id not in sessions:
                    sessions[session_id] = {"caller": "unbekannt", "messages": []}
                data = sessions[session_id]
                messages = data.get("messages", [])
                already_thanked = data.get("thanked", False)

            if messages and not already_thanked:
                with sessions_lock:
                    sessions[session_id]["thanked"] = True
                notify_clawdbot(data.get("caller", "unbekannt"), messages)
                return {
                    "type": "speak",
                    "session_id": session_id,
                    "text": THANKS
                }
            elif not messages:
                return {
                    "type": "speak",
                    "session_id": session_id,
                    "text": "Hallo? Wenn du eine Nachricht hinterlassen möchtest, sprich einfach los.",
                    "user_input_timeout_seconds": 15
                }
            return None

        elif event_type == "session_end":
            print("  📞 Anruf beendet.", flush=True)
            with sessions_lock:
                data = sessions.pop(session_id, {})
                messages = data.get("messages", [])
                caller = data.get("caller", "unbekannt")
                already_thanked = data.get("thanked", False)

            if not already_thanked:
                notify_clawdbot(caller, messages)
            return None

        elif event_type == "assistant_speak":
            return None

        elif event_type == "assistant_speech_ended":
            # Play beep after greeting
            with sessions_lock:
                data = sessions.get(session_id, {})
                if not data.get("beeped") and BEEP_AUDIO:
                    data["beeped"] = True
                    return {
                        "type": "audio",
                        "session_id": session_id,
                        "audio": BEEP_AUDIO
                    }
            return None

        return None

    def log_message(self, format, *args):
        pass


def main():
    server = HTTPServer(("0.0.0.0", PORT), FlowHandler)
    print(f"🍋 YuzuHub Anrufbeantworter läuft auf Port {PORT}", flush=True)
    print(f"   Endpoint: http://0.0.0.0:{PORT}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBeendet.")
        server.server_close()


if __name__ == "__main__":
    main()
