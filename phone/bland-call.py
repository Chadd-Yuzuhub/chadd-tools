#!/usr/bin/env python3
"""Bland.ai outbound call script."""

import argparse
import json
import os
import sys
import requests

# Load from env file
env_file = os.path.expanduser("~/.chadd-mail.env")
if os.path.exists(env_file):
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

API_KEY = os.getenv("BLAND_API_KEY")
BASE_URL = "https://api.bland.ai/v1"

def send_call(phone_number, task, language="de", voice="Florian",
              first_sentence=None, wait_for_greeting=True):
    """Send an outbound call via Bland.ai."""
    headers = {
        "Authorization": API_KEY,
        "Content-Type": "application/json"
    }
    
    payload = {
        "phone_number": phone_number,
        "task": task,
        "language": language,
        "voice": voice,
        "wait_for_greeting": wait_for_greeting,
        "model": "base",
    }
    
    if first_sentence:
        payload["first_sentence"] = first_sentence
    
    resp = requests.post(f"{BASE_URL}/calls", headers=headers, json=payload)
    data = resp.json()
    
    if resp.status_code == 200 and data.get("status") == "success":
        print(f"✅ Call initiated!")
        print(f"   Call ID: {data.get('call_id')}")
        print(f"   Phone: {phone_number}")
    else:
        print(f"❌ Error: {json.dumps(data, indent=2)}")
    
    return data

def get_call(call_id):
    """Get call details and transcript."""
    headers = {"Authorization": API_KEY}
    resp = requests.get(f"{BASE_URL}/calls/{call_id}", headers=headers)
    return resp.json()

def main():
    parser = argparse.ArgumentParser(description="Bland.ai outbound calls")
    sub = parser.add_subparsers(dest="command")
    
    # Send call
    send = sub.add_parser("call", help="Send a call")
    send.add_argument("phone", help="Phone number (E.164 format)")
    send.add_argument("--task", required=True, help="Task/prompt for the AI")
    send.add_argument("--voice", default="Florian", help="Voice (default: Florian)")
    send.add_argument("--lang", default="de", help="Language (default: de)")
    send.add_argument("--first", help="First sentence")
    send.add_argument("--no-wait", action="store_true", help="Don't wait for greeting")
    
    # Get call details
    get = sub.add_parser("status", help="Get call status/transcript")
    get.add_argument("call_id", help="Call ID")
    
    args = parser.parse_args()
    
    if args.command == "call":
        send_call(
            args.phone, args.task,
            language=args.lang, voice=args.voice,
            first_sentence=args.first,
            wait_for_greeting=not args.no_wait
        )
    elif args.command == "status":
        data = get_call(args.call_id)
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
