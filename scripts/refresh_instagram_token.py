"""
Refreshes the Instagram long-lived access token before each daily run and
writes the new token back to this repo's GitHub Actions secrets, so the
pipeline never needs a human to re-authorize Instagram.

Unlike TikTok, Instagram's long-lived token isn't paired with a separate
rotating refresh_token -- you refresh the SAME token in place via
graph.instagram.com/refresh_access_token, and each refresh extends its life
by another ~60 days. The only requirement is that the token be at least 24h
old (and not yet expired) when you refresh it -- running this daily keeps it
comfortably inside that window forever.

Runs as its own workflow step, before the main pipeline. If it fails (for
example IG_ACCESS_TOKEN has expired/been revoked, or the one-time setup in
SETUP_CROSSPOST.md hasn't been done yet), it prints a clear warning and
exits 0 so the rest of the daily run (TikTok, etc.) still goes ahead --
Instagram cross-posting just gets skipped for that run via the existing
IG_CROSSPOST_ENABLED check in src/config.py, using whatever token is
already in repo secrets (which may still be valid even if this refresh
attempt failed).
"""
import base64
import os

import requests

REFRESH_URL = "https://graph.instagram.com/refresh_access_token"
GITHUB_API = "https://api.github.com"


def refresh_instagram_token(access_token):
    resp = requests.get(
        REFRESH_URL,
        params={"grant_type": "ig_refresh_token", "access_token": access_token},
        timeout=30,
    )
    resp.raise_for_status()
    body = resp.json()
    if "access_token" not in body:
        raise RuntimeError(f"unexpected response body: {body}")
    return body["access_token"]


def update_github_secret(repo, pat, secret_name, secret_value):
    headers = {
        "Authorization": f"Bearer {pat}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    key_resp = requests.get(
        f"{GITHUB_API}/repos/{repo}/actions/secrets/public-key",
        headers=headers,
        timeout=30,
    )
    key_resp.raise_for_status()
    key_data = key_resp.json()

    from nacl import encoding, public  # local import: only needed on this path

    public_key = public.PublicKey(key_data["key"].encode("utf-8"), encoding.Base64Encoder())
    sealed_box = public.SealedBox(public_key)
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    encrypted_b64 = base64.b64encode(encrypted).decode("utf-8")

    put_resp = requests.put(
        f"{GITHUB_API}/repos/{repo}/actions/secrets/{secret_name}",
        headers=headers,
        json={"encrypted_value": encrypted_b64, "key_id": key_data["key_id"]},
        timeout=30,
    )
    put_resp.raise_for_status()


def main():
    access_token = os.environ.get("IG_ACCESS_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    pat = os.environ.get("GH_SECRETS_PAT", "")
    github_env_path = os.environ.get("GITHUB_ENV", "")

    if not access_token:
        print(
            "[refresh_instagram_token] Instagram auto-refresh isn't set up yet "
            "(missing IG_ACCESS_TOKEN repo secret) -- skipping. Instagram "
            "cross-posting will be skipped this run. See SETUP_CROSSPOST.md "
            "to enable it (one-time)."
        )
        return

    try:
        new_access_token = refresh_instagram_token(access_token)
    except Exception as exc:
        print(
            f"[refresh_instagram_token] refresh call failed: {exc}. Falling back "
            "to the existing IG_ACCESS_TOKEN for this run (it may still be "
            "valid). If this keeps happening, the token has likely expired or "
            "been revoked and needs to be re-authorized (SETUP_CROSSPOST.md)."
        )
        if github_env_path:
            with open(github_env_path, "a") as f:
                f.write(f"IG_ACCESS_TOKEN={access_token}\n")
        return

    print("[refresh_instagram_token] got a fresh long-lived access_token from Instagram.")

    if github_env_path:
        with open(github_env_path, "a") as f:
            f.write(f"IG_ACCESS_TOKEN={new_access_token}\n")
    else:
        print("[refresh_instagram_token] WARNING: $GITHUB_ENV not set (not running in Actions?), can't hand the fresh token to the next step.")

    if repo and pat:
        try:
            update_github_secret(repo, pat, "IG_ACCESS_TOKEN", new_access_token)
            print("[refresh_instagram_token] persisted the new access_token to repo secrets for tomorrow.")
        except Exception as exc:
            print(
                f"[refresh_instagram_token] WARNING: refreshed OK for today's run, but "
                f"failed to save the new token back to repo secrets ({exc}). "
                "Future refreshes will keep working off the old token until this "
                "is fixed -- check that GH_SECRETS_PAT is a valid, non-expired "
                "token with 'Secrets: write' access to this repo."
            )
    else:
        print(
            "[refresh_instagram_token] WARNING: GH_SECRETS_PAT repo secret isn't "
            "set -- got a fresh token for today's run but can't persist it, so "
            "it'll fall back to the old one next time. See SETUP_CROSSPOST.md."
        )


if __name__ == "__main__":
    main()
