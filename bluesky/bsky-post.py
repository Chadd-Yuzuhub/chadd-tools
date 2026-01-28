#!/usr/bin/env python3
"""Bluesky posting script."""

import json
import os
import sys
from atproto import Client

# Load credentials
env = {}
with open(os.path.expanduser("~/.chadd-mail.env")) as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()

HANDLE = env.get("BSKY_HANDLE", "chadd-yuzu.bsky.social")
PASSWORD = env.get("BSKY_PASS")

def post(text):
    """Post to Bluesky."""
    client = Client()
    client.login(HANDLE, PASSWORD)
    resp = client.send_post(text)
    print(f"✅ Posted!")
    print(f"   URI: {resp.uri}")
    print(f"   URL: https://bsky.app/profile/{HANDLE}/post/{resp.uri.split('/')[-1]}")
    return resp

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("Usage: python3 bsky-post.py 'Your post text'")
        sys.exit(0 if sys.argv[1:] and sys.argv[1] in ("-h", "--help") else 1)
    post(" ".join(sys.argv[1:]))
