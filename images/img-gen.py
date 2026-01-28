#!/usr/bin/env python3
"""Generate images via Freepik Mystic API."""
import json
import os
import sys
import time
import urllib.request
import urllib.error
import argparse

API_KEY = os.environ.get("FREEPIK_API_KEY", "")
if not API_KEY:
    env_file = os.path.expanduser("~/.chadd-mail.env")
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                if line.startswith("FREEPIK_API_KEY="):
                    API_KEY = line.strip().split("=", 1)[1]

BASE_URL = "https://api.freepik.com"


def api_request(method, path, data=None):
    url = f"{BASE_URL}{path}"
    headers = {
        "x-freepik-api-key": API_KEY,
        "Content-Type": "application/json"
    }
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def generate(prompt, resolution="2k", aspect_ratio="square_1_1", realism=True, output=None):
    print(f"Generating: {prompt[:80]}...", file=sys.stderr)
    
    result = api_request("POST", "/v1/ai/mystic", {
        "prompt": prompt,
        "resolution": resolution,
        "aspect_ratio": aspect_ratio,
        "realism": realism,
        "engine": "automatic"
    })
    
    task_id = result.get("data", {}).get("task_id") or result.get("task_id")
    if not task_id:
        # Maybe it returned the image directly
        print(json.dumps(result, indent=2))
        return result
    
    print(f"Task: {task_id}", file=sys.stderr)
    
    # Poll for completion
    for _ in range(60):
        time.sleep(2)
        status = api_request("GET", f"/v1/ai/mystic/{task_id}")
        state = status.get("data", {}).get("status") or status.get("status", "")
        
        if state == "COMPLETED":
            images = status.get("data", {}).get("images") or status.get("images", [])
            if images and output:
                # Download first image
                img_url = images[0].get("url") or images[0]
                urllib.request.urlretrieve(img_url, output)
                print(f"Saved to {output}", file=sys.stderr)
            print(json.dumps(status, indent=2))
            return status
        elif state in ("FAILED", "ERROR"):
            print(f"Failed: {status}", file=sys.stderr)
            return status
        
        print(f"  Status: {state}...", file=sys.stderr)
    
    print("Timeout", file=sys.stderr)
    return None


def main():
    parser = argparse.ArgumentParser(description="Generate images via Freepik Mystic")
    parser.add_argument("prompt", help="Image description")
    parser.add_argument("--resolution", default="2k", choices=["2k", "4k"])
    parser.add_argument("--aspect", default="square_1_1",
                        choices=["square_1_1", "classic_4_3", "traditional_3_4", "widescreen_16_9", "social_story_9_16"])
    parser.add_argument("--no-realism", action="store_true")
    parser.add_argument("-o", "--output", help="Save image to file")
    args = parser.parse_args()
    
    generate(args.prompt, args.resolution, args.aspect, not args.no_realism, args.output)


if __name__ == "__main__":
    main()
