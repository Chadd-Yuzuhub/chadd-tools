#!/usr/bin/env python3
"""Check IMAP inbox for unread messages."""
import imaplib
import email
import email.header
import os
import sys
import json

def decode_header(raw):
    parts = email.header.decode_header(raw or "")
    result = []
    for part, enc in parts:
        if isinstance(part, bytes):
            result.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            result.append(part)
    return " ".join(result)

def get_body(msg):
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain":
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        charset = msg.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace") if payload else ""
    return ""

def main():
    env_file = os.path.expanduser("~/.chadd-mail.env")
    env = {}
    with open(env_file) as f:
        for line in f:
            if "=" in line:
                k, v = line.strip().split("=", 1)
                env[k] = v

    unseen_only = "--all" not in sys.argv
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 10

    imap = imaplib.IMAP4_SSL(env["MAIL_IMAP"], 993)
    imap.login(env["MAIL_USER"], env["MAIL_PASS"])
    imap.select("INBOX")

    criteria = "UNSEEN" if unseen_only else "ALL"
    _, data = imap.search(None, criteria)
    ids = data[0].split()

    if not ids:
        print("No messages." if unseen_only else "Inbox empty.")
        imap.logout()
        return

    results = []
    for mid in ids[-limit:]:
        _, msg_data = imap.fetch(mid, "(BODY.PEEK[])")
        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)
        results.append({
            "id": mid.decode(),
            "from": decode_header(msg["From"]),
            "to": decode_header(msg["To"]),
            "subject": decode_header(msg["Subject"]),
            "date": msg["Date"],
            "body": get_body(msg)[:2000]
        })

    print(json.dumps(results, ensure_ascii=False, indent=2))
    imap.logout()

if __name__ == "__main__":
    main()
