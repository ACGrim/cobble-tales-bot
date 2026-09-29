#!/usr/bin/env python3
"""One-time manual utility: (re-)authorize the TikTok app for your account
and get a new TIKTOK_REFRESH_TOKEN that includes the permissions the
pipeline needs -- video.publish (Direct Post) AND video.upload (send videos
to your TikTok inbox as drafts, which is how videos get posted publicly
before TikTok has audited the app). See SETUP.md Part 6.

This is NOT part of the automated daily pipeline -- run it by hand. Uses only
the Python standard library, so nothing needs installing.

Step 1 -- print the link to approve in your browser:
    python3 scripts/authorize_tiktok.py url --client-key <KEY> --redirect-uri <URI>

  Open it while logged into the TikTok account the bot posts to, approve,
  and you land on your OAuth callback page, which shows a `code`.

Step 2 -- swap that code for tokens (within a few minutes; codes expire fast):
    python3 scripts/authorize_tiktok.py exchange <CODE> --client-key <KEY> --redirect-uri <URI>

  You'll be prompted for the client secret (hidden, not saved anywhere).
  Save the printed refresh token as the TIKTOK_REFRESH_TOKEN repo secret.

<KEY> is the Client Key from developers.tiktok.com -> your app. <URI> must
be EXACTLY the Redirect URI registered under the app's Login Kit settings
(the same one used the first time). TIKTOK_CLIENT_KEY / TIKTOK_REDIRECT_URI
environment variables work instead of the flags.
"""
import argparse
import getpass
import json
import os
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request

AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
DEFAULT_SCOPES = "user.info.basic,video.publish,video.upload"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["url", "exchange"])
    ap.add_argument("code", nargs="?", help="the `code` from the callback page (exchange step)")
    ap.add_argument("--client-key", default=os.environ.get("TIKTOK_CLIENT_KEY", ""))
    ap.add_argument("--redirect-uri", default=os.environ.get("TIKTOK_REDIRECT_URI", ""))
    ap.add_argument("--scopes", default=DEFAULT_SCOPES,
                    help=f"comma-separated (default: {DEFAULT_SCOPES})")
    args = ap.parse_args()
    if not (args.client_key and args.redirect_uri):
        ap.error("--client-key and --redirect-uri are required (or set TIKTOK_CLIENT_KEY / TIKTOK_REDIRECT_URI)")

    if args.step == "url":
        query = urllib.parse.urlencode({
            "client_key": args.client_key,
            "response_type": "code",
            "scope": args.scopes,
            "redirect_uri": args.redirect_uri,
            "state": secrets.token_urlsafe(16),
        })
        print("\nOpen this link while logged into the TikTok account the bot posts to:\n")
        print(f"{AUTHORIZE_URL}?{query}\n")
        print("If TikTok says a scope isn't allowed, turn on that permission for the app")
        print("in the developer portal first (SETUP.md Part 6).")
        return

    if not args.code:
        ap.error("the exchange step needs the code from the callback page")
    client_secret = getpass.getpass("TikTok client secret (hidden, not saved): ").strip()
    if not client_secret:
        sys.exit("No secret entered, aborting.")

    data = urllib.parse.urlencode({
        "client_key": args.client_key,
        "client_secret": client_secret,
        # The callback page already decodes it, but a code copied straight
        # out of the address bar is still percent-encoded.
        "code": urllib.parse.unquote(args.code.strip()),
        "grant_type": "authorization_code",
        "redirect_uri": args.redirect_uri,
    }).encode()
    req = urllib.request.Request(
        TOKEN_URL, data=data, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            body = json.load(resp)
    except urllib.error.HTTPError as e:
        sys.exit(f"Code exchange failed: {e.code} {e.read().decode()}")

    if "refresh_token" not in body:
        sys.exit(f"Code exchange failed: {body}")

    scopes = body.get("scope", "")
    print("\nSuccess. Save this as the TIKTOK_REFRESH_TOKEN repo secret (replace the old value):\n")
    print(f"TIKTOK_REFRESH_TOKEN={body['refresh_token']}")
    print(f"\nPermissions granted: {scopes}")
    missing = [s for s in ("video.publish", "video.upload") if s not in scopes.split(",")]
    if missing:
        print(f"WARNING: missing {', '.join(missing)} -- enable it for the app in the "
              f"developer portal, then run both steps again.")
    print("\n(The daily workflow refreshes the access token from this automatically.)")


if __name__ == "__main__":
    main()
