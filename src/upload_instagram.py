"""
Publishes a finished Short to Instagram as a Reel via the Instagram
Platform API (the current "Instagram API with Instagram Login" product --
NOT the older Facebook Login / linked-Page flow). Three-step flow: create
a media container pointing at a public video URL (Instagram's servers
fetch it from there), poll until Instagram finishes downloading/
processing it, then publish the container.

Needs an Instagram professional (Business or Creator) account, and a Meta
app with the Instagram product's Business Login configured, requesting
instagram_business_basic and instagram_business_content_publish. No linked
Facebook Page is required with this flow. Because the target account has a
direct role on the app (added as the app's own account during Business
Login), this runs under Standard Access and needs no Meta App Review --
same idea as TikTok's unaudited Sandbox posting to its own target user.
See SETUP_CROSSPOST.md.
"""
import time

import requests

from . import config

GRAPH_API_BASE = "https://graph.instagram.com/v25.0"
POLL_INTERVAL_SECONDS = 10
MAX_POLL_ATTEMPTS = 30  # ~5 minutes


def upload(video_url, caption):
    config.require("IG_ACCESS_TOKEN", "IG_USER_ID")

    # 1. Create the media container
    create_resp = requests.post(
        f"{GRAPH_API_BASE}/{config.IG_USER_ID}/media",
        data={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption[:2200],
            "access_token": config.IG_ACCESS_TOKEN,
        },
        timeout=30,
    )
    _raise_for_graph_error(create_resp)
    container_id = create_resp.json()["id"]
    print(f"[upload_instagram] container created: {container_id}")

    # 2. Poll until Instagram has finished downloading/processing the video
    status_url = f"{GRAPH_API_BASE}/{container_id}"
    for attempt in range(1, MAX_POLL_ATTEMPTS + 1):
        time.sleep(POLL_INTERVAL_SECONDS)
        status_resp = requests.get(
            status_url,
            params={"fields": "status_code", "access_token": config.IG_ACCESS_TOKEN},
            timeout=30,
        )
        _raise_for_graph_error(status_resp)
        status_code = status_resp.json().get("status_code")
        print(f"[upload_instagram] container status: {status_code} (attempt {attempt}/{MAX_POLL_ATTEMPTS})")
        if status_code == "FINISHED":
            break
        if status_code == "ERROR":
            raise RuntimeError(f"Instagram failed to process the video (container {container_id})")
    else:
        raise RuntimeError(f"Instagram container {container_id} never finished processing in time")

    # 3. Publish it
    publish_resp = requests.post(
        f"{GRAPH_API_BASE}/{config.IG_USER_ID}/media_publish",
        data={"creation_id": container_id, "access_token": config.IG_ACCESS_TOKEN},
        timeout=30,
    )
    _raise_for_graph_error(publish_resp)
    media_id = publish_resp.json()["id"]
    print(f"[upload_instagram] published: media id {media_id}")
    return media_id


def _raise_for_graph_error(resp):
    if resp.status_code >= 400:
        raise RuntimeError(f"Instagram Graph API error {resp.status_code}: {resp.text[:500]}")
