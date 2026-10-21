"""
Checks every credential the daily run depends on, WITHOUT posting anything,
and prints a plain report: what works, what doesn't, and the exact error the
service returned. Token values are never printed.

Run it from the Actions tab ("Check tokens" workflow) whenever the daily run
logs a token warning.
"""
import os
import sys

import requests

TIKTOK_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
IG_BASE = "https://graph.instagram.com"
GITHUB_API = "https://api.github.com"

problems = []


def report(ok, name, detail):
    print(f"{'OK  ' if ok else 'FAIL'}  {name}: {detail}")
    if not ok:
        problems.append(name)


def body_of(resp):
    try:
        return resp.json()
    except Exception:
        return resp.text[:400]


def check_github_pat():
    pat = os.environ.get("GH_SECRETS_PAT", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not pat:
        report(False, "GH_SECRETS_PAT", "secret is not set")
        return
    h = {"Authorization": f"Bearer {pat}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    who = requests.get(f"{GITHUB_API}/user", headers=h, timeout=30)
    if who.status_code == 401:
        report(False, "GH_SECRETS_PAT", "GitHub rejects this token (401 Bad credentials): it is expired, revoked, or was pasted wrong. Create a new one.")
        return
    exp = who.headers.get("github-authentication-token-expiration", "no expiry date reported")
    key = requests.get(f"{GITHUB_API}/repos/{repo}/actions/secrets/public-key", headers=h, timeout=30)
    if key.status_code == 200:
        report(True, "GH_SECRETS_PAT", f"valid, can read {repo} secrets key (token expires: {exp})")
    else:
        report(False, "GH_SECRETS_PAT", f"token is valid but can't access {repo} secrets ({key.status_code}): give it 'Secrets: Read and write' on this repo. Response: {body_of(key)}")


def check_tiktok():
    ck, cs, rt = (os.environ.get(k, "").strip() for k in ("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_REFRESH_TOKEN"))
    if not (ck and cs and rt):
        report(False, "TikTok", "TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET / TIKTOK_REFRESH_TOKEN not all set")
        return
    r = requests.post(TIKTOK_TOKEN_URL, headers={"Content-Type": "application/x-www-form-urlencoded"},
                      data={"client_key": ck, "client_secret": cs, "grant_type": "refresh_token", "refresh_token": rt}, timeout=30)
    b = body_of(r)
    if r.status_code != 200 or not isinstance(b, dict) or "access_token" not in b:
        report(False, "TikTok", f"refresh failed ({r.status_code}): {b}")
        return
    same = b.get("refresh_token") == rt
    days = int(b.get("refresh_expires_in", 0)) // 86400
    report(True, "TikTok", f"refresh works; TikTok returned {'the SAME' if same else 'a NEW'} refresh token, valid for ~{days} more days; scopes: {b.get('scope')}")


def check_instagram():
    raw = os.environ.get("IG_ACCESS_TOKEN", "")
    tok = raw.strip()
    if raw != tok:
        print("NOTE  IG_ACCESS_TOKEN secret has extra spaces/line breaks around it (the scripts now trim them)")
    if not tok:
        report(False, "Instagram", "IG_ACCESS_TOKEN not set")
        return
    me = requests.get(f"{IG_BASE}/v25.0/me", params={"fields": "user_id,username,account_type", "access_token": tok}, timeout=30)
    if me.status_code == 200:
        b = me.json()
        report(True, "Instagram token", f"valid for @{b.get('username')} ({b.get('account_type')})")
    else:
        report(False, "Instagram token", f"rejected ({me.status_code}): {body_of(me)}")
    rf = requests.get(f"{IG_BASE}/refresh_access_token", params={"grant_type": "ig_refresh_token", "access_token": tok}, timeout=30)
    b = body_of(rf)
    if rf.status_code == 200 and isinstance(b, dict) and "access_token" in b:
        same = b["access_token"] == tok
        report(True, "Instagram refresh", f"works; Instagram returned {'the SAME' if same else 'a NEW'} token, valid ~{int(b.get('expires_in', 0)) // 86400} days")
    else:
        report(False, "Instagram refresh", f"failed ({rf.status_code}): {b}")


if __name__ == "__main__":
    for fn in (check_github_pat, check_tiktok, check_instagram):
        try:
            fn()
        except Exception as exc:  # keep checking the rest
            report(False, fn.__name__, f"check crashed: {exc}")
    print()
    print("All credentials OK." if not problems else f"Needs attention: {', '.join(problems)}")
    sys.exit(1 if problems else 0)
