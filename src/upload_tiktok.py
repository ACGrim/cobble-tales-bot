"""
Publishes a finished video to TikTok via the Content Posting API, pulling the
video from a public URL (same idea as the Instagram uploader -- TikTok's
servers fetch it, no direct file upload).

Visibility: posts go out as config.TIKTOK_PRIVACY_LEVEL (PUBLIC_TO_EVERYONE by
default). Before posting, the uploader asks TikTok which privacy levels this
account may use (creator_info). If public isn't allowed, or TikTok refuses
the public post (for example a developer app that hasn't passed TikTok's
audit can only post privately), config.TIKTOK_FALLBACK decides what happens
so the video still goes up:
  "inbox"   -- the video is sent to the TikTok app's inbox; open the
               notification in TikTok to post it publicly
  "private" -- it's posted as SELF_ONLY (visible only to you)
"""
import time

import requests

from . import config

API = "https://open.tiktokapis.com/v2"
CREATOR_INFO_URL = f"{API}/post/publish/creator_info/query/"
INIT_URL = f"{API}/post/publish/video/init/"
INBOX_INIT_URL = f"{API}/post/publish/inbox/video/init/"
STATUS_URL = f"{API}/post/publish/status/fetch/"
POLL_INTERVAL_SECONDS = 10
MAX_POLL_ATTEMPTS = 30  # ~5 minutes

# TikTok error codes that mean "you can't post this publicly", as opposed to
# a broken token or a bad video.
_PRIVACY_REFUSALS = {
    "unaudited_client_can_only_post_to_private_accounts",
    "privacy_level_option_mismatch",
}


class TikTokError(RuntimeError):
    def __init__(self, status, code, message):
        super().__init__(f"TikTok API error {status} {code}: {message}")
        self.code = code


def _headers():
    return {
        "Authorization": f"Bearer {config.TIKTOK_ACCESS_TOKEN}",
        "Content-Type": "application/json; charset=UTF-8",
    }


def _check(resp):
    try:
        body = resp.json()
    except ValueError:
        body = {}
    err = body.get("error", {}) if isinstance(body, dict) else {}
    code = err.get("code")
    if resp.status_code >= 400 or code not in (None, "ok"):
        raise TikTokError(resp.status_code, code, err.get("message") or resp.text[:500])
    return body


def _privacy_options():
    try:
        body = _check(requests.post(CREATOR_INFO_URL, headers=_headers(), timeout=30))
        data = body.get("data", {})
        print(f"[upload_tiktok] @{data.get('creator_username')} may post as {data.get('privacy_level_options')}")
        return data.get("privacy_level_options") or []
    except Exception as exc:  # not fatal: just try the configured level
        print(f"[upload_tiktok] couldn't read creator info ({exc}); trying {config.TIKTOK_PRIVACY_LEVEL} anyway")
        return []


def _direct_post(video_url, title, privacy):
    body = _check(requests.post(
        INIT_URL,
        headers=_headers(),
        json={
            "post_info": {
                "title": title[:2200],
                "privacy_level": privacy,
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
                "is_aigc": config.TIKTOK_IS_AIGC,
            },
            "source_info": {"source": "PULL_FROM_URL", "video_url": video_url},
        },
        timeout=30,
    ))
    return body["data"]["publish_id"]


def _inbox_upload(video_url):
    body = _check(requests.post(
        INBOX_INIT_URL,
        headers=_headers(),
        json={"source_info": {"source": "PULL_FROM_URL", "video_url": video_url}},
        timeout=30,
    ))
    return body["data"]["publish_id"]


def _wait(publish_id, done_states):
    for attempt in range(1, MAX_POLL_ATTEMPTS + 1):
        time.sleep(POLL_INTERVAL_SECONDS)
        body = _check(requests.post(STATUS_URL, headers=_headers(), json={"publish_id": publish_id}, timeout=30))
        status = body.get("data", {}).get("status")
        print(f"[upload_tiktok] status: {status} (attempt {attempt}/{MAX_POLL_ATTEMPTS})")
        if status in done_states:
            return status
        if status == "FAILED":
            raise RuntimeError(f"TikTok publish failed (publish_id {publish_id}): {body}")
    raise RuntimeError(f"TikTok publish {publish_id} never completed in time")


def _fallback(video_url, title, reason):
    if config.TIKTOK_FALLBACK == "private":
        print(f"[upload_tiktok] {reason} -- posting as SELF_ONLY (only you can see it).")
        pid = _direct_post(video_url, title, "SELF_ONLY")
        _wait(pid, {"PUBLISH_COMPLETE"})
        print(f"[upload_tiktok] published PRIVATELY: publish_id {pid}")
        return pid
    print(f"[upload_tiktok] {reason} -- sending the video to your TikTok inbox instead; "
          f"open the TikTok app notification to post it publicly.")
    pid = _inbox_upload(video_url)
    _wait(pid, {"SEND_TO_USER_INBOX", "PUBLISH_COMPLETE"})
    print(f"[upload_tiktok] sent to TikTok inbox: publish_id {pid}")
    return pid


def upload(video_url, title):
    config.require("TIKTOK_ACCESS_TOKEN")
    privacy = config.TIKTOK_PRIVACY_LEVEL
    options = _privacy_options()
    if options and privacy not in options:
        return _fallback(video_url, title, f"TikTok doesn't allow {privacy} for this account (allowed: {options})")
    try:
        publish_id = _direct_post(video_url, title, privacy)
    except TikTokError as exc:
        if exc.code in _PRIVACY_REFUSALS:
            return _fallback(video_url, title, f"TikTok refused a {privacy} post ({exc.code})")
        raise
    print(f"[upload_tiktok] publish initiated as {privacy}: {publish_id}")
    _wait(publish_id, {"PUBLISH_COMPLETE"})
    print(f"[upload_tiktok] published as {privacy}: publish_id {publish_id}")
    return publish_id
