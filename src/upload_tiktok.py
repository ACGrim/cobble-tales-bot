"""
Publishes a finished Short to TikTok via the Content Posting API's Direct
Post endpoint, pulling the video from a public URL (same idea as the
Instagram uploader -- TikTok's servers fetch it, no direct file upload).

IMPORTANT: until your TikTok developer app passes TikTok's audit, every
video posted through this endpoint is forced to SELF_ONLY visibility --
visible only to the account that authorized the app, never public,
regardless of what TIKTOK_PRIVACY_LEVEL is set to. Flip it to
"PUBLIC_TO_EVERYONE" in your repo Secrets once TikTok approves the app.
See SETUP_CROSSPOST.md for how to register the app and start that audit.
"""
import time

import requests

from . import config

INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
POLL_INTERVAL_SECONDS = 10
MAX_POLL_ATTEMPTS = 30  # ~5 minutes


def upload(video_url, title):
    config.require("TIKTOK_ACCESS_TOKEN")

    headers = {
        "Authorization": f"Bearer {config.TIKTOK_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    init_resp = requests.post(
        INIT_URL,
        headers=headers,
        json={
            "post_info": {
                "title": title[:2200],
                "privacy_level": config.TIKTOK_PRIVACY_LEVEL,
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
            },
            "source_info": {
                "source": "PULL_FROM_URL",
                "video_url": video_url,
            },
        },
        timeout=30,
    )
    _raise_for_tiktok_error(init_resp)
    publish_id = init_resp.json()["data"]["publish_id"]
    print(f"[upload_tiktok] publish initiated: {publish_id}")

    for attempt in range(1, MAX_POLL_ATTEMPTS + 1):
        time.sleep(POLL_INTERVAL_SECONDS)
        status_resp = requests.post(
            STATUS_URL, headers=headers, json={"publish_id": publish_id}, timeout=30
        )
        _raise_for_tiktok_error(status_resp)
        status = status_resp.json().get("data", {}).get("status")
        print(f"[upload_tiktok] status: {status} (attempt {attempt}/{MAX_POLL_ATTEMPTS})")
        if status == "PUBLISH_COMPLETE":
            break
        if status == "FAILED":
            raise RuntimeError(f"TikTok publish failed (publish_id {publish_id}): {status_resp.text[:500]}")
    else:
        raise RuntimeError(f"TikTok publish {publish_id} never completed in time")

    print(f"[upload_tiktok] published: publish_id {publish_id}")
    return publish_id


def _raise_for_tiktok_error(resp):
    if resp.status_code >= 400:
        raise RuntimeError(f"TikTok API error {resp.status_code}: {resp.text[:500]}")
    body = resp.json()
    err_code = body.get("error", {}).get("code")
    if err_code not in (None, "ok"):
        raise RuntimeError(f"TikTok API error: {body['error']}")
