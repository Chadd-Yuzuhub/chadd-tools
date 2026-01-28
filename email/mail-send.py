#!/usr/bin/env python3
"""Send an email via SMTP."""
import smtplib
import ssl
import os
import sys
import argparse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def main():
    parser = argparse.ArgumentParser(description="Send email")
    parser.add_argument("--to", required=True, help="Recipient email")
    parser.add_argument("--subject", required=True, help="Subject line")
    parser.add_argument("--body", required=True, help="Email body")
    parser.add_argument("--html", action="store_true", help="Send as HTML")
    parser.add_argument("--cc", help="CC recipient email")
    parser.add_argument("--reply-to", help="In-Reply-To message ID")
    args = parser.parse_args()

    env_file = os.path.expanduser("~/.chadd-mail.env")
    env = {}
    with open(env_file) as f:
        for line in f:
            if "=" in line:
                k, v = line.strip().split("=", 1)
                env[k] = v

    msg = MIMEMultipart("alternative") if args.html else MIMEText(args.body, "plain", "utf-8")
    if args.html:
        msg.attach(MIMEText(args.body, "html", "utf-8"))

    msg["From"] = f"Chadd <{env['MAIL_USER']}>"
    msg["To"] = args.to
    msg["Subject"] = args.subject
    if args.cc:
        msg["Cc"] = args.cc
    if args.reply_to:
        msg["In-Reply-To"] = args.reply_to
        msg["References"] = args.reply_to

    recipients = [args.to]
    if args.cc:
        recipients.append(args.cc)

    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(env["MAIL_SMTP"], 465, context=ctx) as s:
        s.login(env["MAIL_USER"], env["MAIL_PASS"])
        s.sendmail(env["MAIL_USER"], recipients, msg.as_string())
    
    print(f"Sent to {args.to}: {args.subject}")

if __name__ == "__main__":
    main()
