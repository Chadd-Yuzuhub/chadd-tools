#!/usr/bin/env python3
"""Check OwnCloud CalDAV calendar for events."""
import os
import sys
import json
import re
from datetime import datetime, timedelta
from urllib.request import Request, urlopen
from urllib.parse import quote

def load_env():
    env = {}
    with open(os.path.expanduser("~/.chadd-mail.env")) as f:
        for line in f:
            if "=" in line:
                k, v = line.strip().split("=", 1)
                env[k] = v
    return env

def caldav_request(url, user, pw, method="PROPFIND", body="", headers=None):
    hdrs = {"Content-Type": "application/xml", "Depth": "1"}
    if headers:
        hdrs.update(headers)
    import base64
    auth = base64.b64encode(f"{user}:{pw}".encode()).decode()
    hdrs["Authorization"] = f"Basic {auth}"
    req = Request(url, data=body.encode() if body else None, headers=hdrs, method=method)
    with urlopen(req) as resp:
        return resp.read().decode()

def parse_ical_events(data):
    """Simple iCal parser — extracts VEVENT blocks."""
    events = []
    in_event = False
    event = {}
    for line in data.replace("\r\n ", "").replace("\r\n\t", "").split("\r\n"):
        if line.strip() == "BEGIN:VEVENT":
            in_event = True
            event = {}
        elif line.strip() == "END:VEVENT":
            in_event = False
            events.append(event)
        elif in_event and ":" in line:
            key, _, val = line.partition(":")
            key = key.split(";")[0]
            event[key] = val
    return events

def parse_dt(s):
    """Parse iCal datetime."""
    s = s.replace("Z", "")
    for fmt in ("%Y%m%dT%H%M%S", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None

def main():
    env = load_env()
    url = env["OWNCLOUD_URL"]
    user = env["OWNCLOUD_USER"]
    pw = env["OWNCLOUD_PASS"]
    
    days = int(sys.argv[sys.argv.index("--days") + 1]) if "--days" in sys.argv else 14
    
    principal = "Chadd%20The%20Bot"
    
    # Check all calendars including shared ones
    calendars = [
        ("Persönlich", f"{url}/remote.php/dav/calendars/{principal}/personal/"),
        ("Stefan", f"{url}/remote.php/dav/calendars/{principal}/personal_shared_by_stefanlh/"),
    ]
    
    if "--calendar" in sys.argv:
        cal_filter = sys.argv[sys.argv.index("--calendar") + 1].lower()
        calendars = [(n, u) for n, u in calendars if cal_filter in n.lower()]
    
    cal_url = None  # will iterate
    
    now = datetime.utcnow()
    start = now.strftime("%Y%m%dT000000Z")
    end = (now + timedelta(days=days)).strftime("%Y%m%dT235959Z")
    
    body = f"""<?xml version="1.0"?>
<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:prop><d:getetag/><c:calendar-data/></d:prop>
  <c:filter>
    <c:comp-filter name="VCALENDAR">
      <c:comp-filter name="VEVENT">
        <c:time-range start="{start}" end="{end}"/>
      </c:comp-filter>
    </c:comp-filter>
  </c:filter>
</c:calendar-query>"""
    
    import xml.etree.ElementTree as ET
    ns = {"d": "DAV:", "c": "urn:ietf:params:xml:ns:caldav"}
    
    all_events = []
    for cal_name, cal_url in calendars:
        try:
            resp = caldav_request(cal_url, user, pw, method="REPORT", body=body, headers={"Depth": "1"})
        except Exception as e:
            print(f"[{cal_name}] Error: {e}", file=sys.stderr)
            continue
        
        root = ET.fromstring(resp)
        for response in root.findall("d:response", ns):
            cal_data = response.find(".//c:calendar-data", ns)
            if cal_data is not None and cal_data.text:
                events = parse_ical_events(cal_data.text)
                for ev in events:
                    dt_start = parse_dt(ev.get("DTSTART", ""))
                    dt_end = parse_dt(ev.get("DTEND", ""))
                    all_events.append({
                        "calendar": cal_name,
                        "summary": ev.get("SUMMARY", "(kein Titel)"),
                        "start": dt_start.isoformat() if dt_start else ev.get("DTSTART", "?"),
                        "end": dt_end.isoformat() if dt_end else ev.get("DTEND", "?"),
                        "location": ev.get("LOCATION", ""),
                        "description": ev.get("DESCRIPTION", "")[:500],
                        "status": ev.get("STATUS", ""),
                    })
    
    all_events.sort(key=lambda e: e["start"])
    
    if not all_events:
        print(f"Keine Termine in den nächsten {days} Tagen.")
    else:
        print(json.dumps(all_events, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
