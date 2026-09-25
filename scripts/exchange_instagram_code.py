#!/usr/bin/env python3
"""One-time manual utility: exchange an Instagram OAuth authorization
`code` (from the business-login consent redirect) for a 60-day
long-lived access token, and print the values you need to save as the
IG_ACCESS_TOKEN and IG_USER_ID GitHub Actions secrets.

This is NOT part of the automated daily pipeline -- run it by hand,
once, after completing the Instagram business login consent flow.

Usage:
    python3 scripts/exchange_instagram_code.py <code>

You will be prompted for the Instagram app secret (hidden input, not
echoed, not saved anywhere). Find it in the Meta App Dashboard under
Cobble Tales Poster -> Instagram API -> API setup with Instagram login
-> "Instagram app secret" -> Show.
"""
import sys
import json
import getpass
import urllib.request
import urllib.parse

APP_ID = "1829007268272826"
REDIRECT_URI = "https://cobble-tales.pages.dev/auth/instagram/callback"


def main():
    if len(sys.argv) != 2:
        print("Usage: exchange_instagram_code.py <code>")
        sys.exit(1)
    code = sys.argv[1]

    app_secret = getpass.getpass("Instagram app secret (hidden, not saved): ").strip()
    if not app_secret:
        print("No secret entered, aborting.")
        sys.exit(1)

    # Step 1: exchange the authorization code for a short-lived token.
    data = urllib.parse.urlencode({
        "client_id": APP_ID,
        "client_secret": app_secret,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
        "code": code,
    }).encode()
    req = urllib.request.Request(
        "https://api.instagram.com/oauth/access_token", data=data, method="POST"
    )
    try:
        with urllib.request.urlopen(req) as resp:
            short = json.load(resp)
    except urllib.error.HTTPError as e:
        print(f"Step 1 (code exchange) failed: {e.code} {e.read().decode()}")
        sys.exit(1)

    short_token = short["access_token"]
    user_id = short["user_id"]

    # Step 2: exchange the short-lived token for a 60-day long-lived token.
    params = urllib.parse.urlencode({
        "grant_type": "ig_exchange_token",
        "client_secret": app_secret,
        "access_token": short_token,
    })
    try:
        with urllib.request.urlopen(
            f"https://graph.instagram.com/access_token?{params}"
        ) as resp:
            long_ = json.load(resp)
    except urllib.error.HTTPError as e:
        print(f"Step 2 (long-lived exchange) failed: {e.code} {e.read().decode()}")
        sys.exit(1)

    long_token = long_["access_token"]
    expires_in_days = long_.get("expires_in", 0) // 86400

    print("\nSuccess. Copy these into GitHub Actions secrets:\n")
    print(f"IG_ACCESS_TOKEN={long_token}")
    print(f"IG_USER_ID={user_id}")
    print(f"\n(long-lived token expires in ~{expires_in_days} days -- "
          f"scripts/refresh_instagram_token.py refreshes it automatically "
          f"in the daily workflow before that.)")


if __name__ == "__main__":
    main()
