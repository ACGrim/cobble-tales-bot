"""
Refreshes the TikTok OAuth access token before each daily run and writes
the new access_token + refresh_token back to this repo's GitHub Actions
secrets, so the pipeline never needs a human to re-authorize TikTok.

TikTok access tokens expire in ~24h. The refresh_token lasts much longer
but TikTok rotates it on every use -- each refresh call invalidates the
old refresh_token and issues a new one -- so the new refresh_token MUST be
saved back to repo secrets every single day, or the next day's refresh
will fail with an invalid_grant error.

Runs as its own workflow step, before the main pipeline. If it fails (for
example TIKTOK_REFRESH_TOKEN itself has gone stale/been revoked, or the
one-time setup in SETUP_CROSSPOST.md Part 5 hasn't been done yet), it
prints a clear warning and exits 0 so the rest of the daily run (YouTube,
Instagram) still goes ahead -- TikTok cross-posting just gets skipped for
that run via the existing TIKTOK_CROSSPOST_ENABLED check in src/config.py.
"""
import base64
import os

import requests

TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
GITHUB_API = "https://api.github.com"


def refresh_tiktok_token(client_key, client_secret, refresh_token):
    resp = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=30,
    )
    resp.raise_for_status()
    body = resp.json()
    if "access_token" not in body or "refresh_token" not in body:
        raise RuntimeError(f"unexpected response body: {body}")
    return body["access_token"], body["refresh_token"], body.get("scope", "")


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
    client_key = os.environ.get("TIKTOK_CLIENT_KEY", "")
    client_secret = os.environ.get("TIKTOK_CLIENT_SECRET", "")
    refresh_token = os.environ.get("TIKTOK_REFRESH_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    pat = os.environ.get("GH_SECRETS_PAT", "")
    github_env_path = os.environ.get("GITHUB_ENV", "")

    if not (client_key and client_secret and refresh_token):
        print(
            "[refresh_tiktok_token] TikTok auto-refresh isn't set up yet "
            "(missing TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET / "
            "TIKTOK_REFRESH_TOKEN repo secrets) -- skipping. TikTok "
            "cross-posting will be skipped this run. See SETUP_CROSSPOST.md "
            "Part 5 to enable it (one-time)."
        )
        return

    try:
        new_access_token, new_refresh_token, scope = refresh_tiktok_token(
            client_key, client_secret, refresh_token
        )
    except Exception as exc:
        print(
            f"[refresh_tiktok_token] refresh call failed: {exc}. TikTok "
            "cross-posting will be skipped this run -- if this keeps "
            "happening, TIKTOK_REFRESH_TOKEN has likely been revoked and "
            "needs to be re-authorized (SETUP_CROSSPOST.md Part 3 + 5)."
        )
        return

    print("[refresh_tiktok_token] got a fresh access_token + refresh_token from TikTok.")
    if scope:
        print(f"[refresh_tiktok_token] permissions on this TikTok login: {scope}")
        if "video.upload" not in scope.split(","):
            print(
                "[refresh_tiktok_token] NOTE: no video.upload permission, so videos "
                "can't be sent to your TikTok inbox as drafts -- with a public "
                "account and an unaudited app, TikTok posts will fail. Re-authorize "
                "with scripts/authorize_tiktok.py (SETUP.md Part 6)."
            )

    if github_env_path:
        with open(github_env_path, "a") as f:
            f.write(f"TIKTOK_ACCESS_TOKEN={new_access_token}\n")
    else:
        print("[refresh_tiktok_token] WARNING: $GITHUB_ENV not set (not running in Actions?), can't hand the fresh token to the next step.")

    if repo and pat:
        try:
            update_github_secret(repo, pat, "TIKTOK_ACCESS_TOKEN", new_access_token)
            update_github_secret(repo, pat, "TIKTOK_REFRESH_TOKEN", new_refresh_token)
            print("[refresh_tiktok_token] persisted the new access_token + refresh_token to repo secrets for tomorrow.")
        except Exception as exc:
            print(
                f"[refresh_tiktok_token] WARNING: refreshed OK for today's run, but "
                f"failed to save the new tokens back to repo secrets ({exc}). "
                "Tomorrow's refresh will fail unless this is fixed -- check that "
                "GH_SECRETS_PAT is a valid, non-expired token with 'Secrets: "
                "write' access to this repo."
            )
    else:
        print(
            "[refresh_tiktok_token] WARNING: GH_SECRETS_PAT repo secret isn't "
            "set -- got a fresh token for today's run but can't persist the "
            "new refresh_token, so tomorrow's refresh will fail (TikTok "
            "invalidates the old refresh_token on every use). See "
            "SETUP_CROSSPOST.md Part 5."
        )


if __name__ == "__main__":
    main()
