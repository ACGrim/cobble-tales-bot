"""
Publishes a finished video to TikTok via the Content Posting API. TikTok's
servers pull the video from a public URL (PULL_FROM_URL) -- same idea as the
Instagram uploader, no direct file upload.

Getting videos PUBLIC -- these are TikTok's rules, not this pipeline's:
  * Audited app: Direct Post publishes PUBLIC_TO_EVERYONE straight to your
    profile, fully automatic. Requires passing TikTok's app audit
    (SETUP.md Part 3).
  * Unaudited app: Direct Post only works while the TikTok account is set to
    PRIVATE, and posts land as "only me" whatever privacy we ask for. With a
    public account TikTok rejects the post outright
    (unaudited_client_can_only_post_to_private_accounts).
  * Any app, audited or not: upload as a DRAFT to your TikTok inbox
    (video.upload scope). TikTok sends you a notification; tap it, paste the
    caption, and post it publicly yourself -- one tap per video.

TIKTOK_POST_MODE picks the strategy:
  auto (default)  Direct Post, as public as your account allows. If TikTok
                  says the app isn't audited yet, send it to your inbox as a
                  draft instead. Once the audit passes, posts go public on
                  their own -- nothing to change.
  direct          Direct Post only (no draft fallback).
  draft           Always send to your inbox as a draft.
"""
import time

import requests

from . import config

API = "https://open.tiktokapis.com/v2/post/publish"
CREATOR_INFO_URL = f"{API}/creator_info/query/"
DIRECT_INIT_URL = f"{API}/video/init/"
INBOX_INIT_URL = f"{API}/inbox/video/init/"
STATUS_URL = f"{API}/status/fetch/"
POLL_INTERVAL_SECONDS = 10
MAX_POLL_ATTEMPTS = 30  # ~5 minutes

# Most to least public; used when the level we want isn't one this account
# is allowed to use (e.g. a private account can't post PUBLIC_TO_EVERYONE).
PRIVACY_PREFERENCE = ["PUBLIC_TO_EVERYONE", "FOLLOWER_OF_CREATOR", "MUTUAL_FOLLOW_FRIENDS", "SELF_ONLY"]

# TikTok's answer when an unaudited app tries to Direct Post to an account
# that isn't private -- the one case auto mode reroutes to a draft.
UNAUDITED_ERRORS = {"unaudited_client_can_only_post_to_private_accounts"}

# Set once TikTok says Direct Post is blocked for this app, so the rest of
# the day's videos go straight to drafts instead of failing first each time.
_direct_blocked = False


class TikTokError(RuntimeError):
    def __init__(self, code, message, http_status=None):
        status = f" {http_status}" if http_status else ""
        super().__init__(f"TikTok API error{status} {code}: {message}")
        self.code = code


def upload(video_url, caption, duration=None):
    """Posts (or drafts) one video. Returns a dict:
      {"kind": "published", "privacy": "PUBLIC_TO_EVERYONE", "publish_id": ...}
      {"kind": "draft", "publish_id": ...}   -- waiting in your TikTok inbox
    """
    global _direct_blocked
    config.require("TIKTOK_ACCESS_TOKEN")
    mode = config.TIKTOK_POST_MODE

    if mode == "draft" or (mode == "auto" and _direct_blocked):
        return _upload_draft(video_url)
    try:
        return _direct_post(video_url, caption, duration)
    except TikTokError as e:
        if mode != "auto" or e.code not in UNAUDITED_ERRORS:
            raise
        _direct_blocked = True
        print("[upload_tiktok] TikTok hasn't audited this app yet, and unaudited apps can't "
              "Direct Post to a public account -- sending the video to your TikTok inbox as "
              "a draft instead. Tap the notification in the TikTok app to post it publicly.")
        return _upload_draft(video_url)


def _direct_post(video_url, caption, duration):
    # TikTok requires querying the creator's current settings before every
    # Direct Post: which privacy levels this account may use, whether
    # comments/duets/stitches are switched off, and the max video length.
    info = _call(CREATOR_INFO_URL, {})
    privacy = _pick_privacy(info.get("privacy_level_options") or [])
    max_len = info.get("max_video_post_duration_sec")
    if duration and max_len and duration > max_len:
        raise TikTokError("video_too_long",
                          f"video is {duration:.0f}s but this account can post at most {max_len}s")

    data = _call(DIRECT_INIT_URL, {
        "post_info": {
            "title": caption[:2200],
            "privacy_level": privacy,
            "disable_duet": bool(info.get("duet_disabled")),
            "disable_comment": bool(info.get("comment_disabled")),
            "disable_stitch": bool(info.get("stitch_disabled")),
        },
        "source_info": {"source": "PULL_FROM_URL", "video_url": video_url},
    })
    publish_id = data["publish_id"]
    print(f"[upload_tiktok] Direct Post initiated ({privacy}): {publish_id}")
    _wait(publish_id, done={"PUBLISH_COMPLETE"})
    print(f"[upload_tiktok] published ({privacy}): publish_id {publish_id}")
    return {"kind": "published", "privacy": privacy, "publish_id": publish_id}


def _upload_draft(video_url):
    try:
        data = _call(INBOX_INIT_URL, {"source_info": {"source": "PULL_FROM_URL", "video_url": video_url}})
    except TikTokError as e:
        if e.code == "scope_not_authorized":
            raise TikTokError(e.code, "the TikTok login doesn't include the video.upload "
                              "permission that drafts need -- re-authorize with "
                              "scripts/authorize_tiktok.py (SETUP.md Part 6)") from e
        if e.code == "spam_risk_too_many_pending_share":
            raise TikTokError(e.code, "too many unposted drafts are waiting in your TikTok "
                              "inbox -- post or delete them in the TikTok app") from e
        raise
    publish_id = data["publish_id"]
    print(f"[upload_tiktok] draft upload initiated: {publish_id}")
    # SEND_TO_USER_INBOX = TikTok has the video and has notified you;
    # PUBLISH_COMPLETE = you already posted it from the app.
    _wait(publish_id, done={"SEND_TO_USER_INBOX", "PUBLISH_COMPLETE"})
    print(f"[upload_tiktok] draft is in your TikTok inbox: publish_id {publish_id}")
    return {"kind": "draft", "publish_id": publish_id}


def _pick_privacy(options):
    wanted = config.TIKTOK_PRIVACY_LEVEL
    if wanted in options or not options:
        return wanted
    start = PRIVACY_PREFERENCE.index(wanted) if wanted in PRIVACY_PREFERENCE else 0
    for level in PRIVACY_PREFERENCE[start:]:
        if level in options:
            print(f"[upload_tiktok] {wanted} isn't available for this account "
                  f"(allowed: {', '.join(options)}) -- using {level}. A private TikTok "
                  f"account can't post publicly; switch it to public in the app.")
            return level
    return options[0]


def _wait(publish_id, done):
    for attempt in range(1, MAX_POLL_ATTEMPTS + 1):
        time.sleep(POLL_INTERVAL_SECONDS)
        data = _call(STATUS_URL, {"publish_id": publish_id})
        status = data.get("status")
        print(f"[upload_tiktok] status: {status} (attempt {attempt}/{MAX_POLL_ATTEMPTS})")
        if status in done:
            return status
        if status == "FAILED":
            raise TikTokError(data.get("fail_reason") or "FAILED", f"publish_id {publish_id} failed")
    raise TikTokError("timeout", f"publish_id {publish_id} never finished processing in time")


def _call(url, payload):
    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {config.TIKTOK_ACCESS_TOKEN}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        json=payload,
        timeout=30,
    )
    try:
        body = resp.json()
    except ValueError:
        body = {}
    err = body.get("error") or {}
    code = err.get("code")
    if resp.status_code >= 400 or code not in (None, "ok"):
        raise TikTokError(code or f"http_{resp.status_code}",
                          err.get("message") or resp.text[:300], resp.status_code)
    return body.get("data") or {}
