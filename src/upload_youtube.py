"""
Uploads a finished video to YouTube as a Short, straight from the local file
(no R2 hosting needed -- unlike Instagram/TikTok, YouTube takes a direct
upload).

Auth is a long-lived OAuth refresh token for the Cobble Tales channel, minted
once on your own computer with scripts/youtube_oauth_setup.py (see
SETUP.md, "YouTube Shorts"). Until YT_CLIENT_ID / YT_CLIENT_SECRET /
YT_REFRESH_TOKEN are set, YouTube uploads are skipped.

A vertical video of 3 minutes or less is treated as a Short automatically;
#Shorts in the description is added as an extra signal.
"""
import time

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from . import config

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]
TOKEN_URI = "https://oauth2.googleapis.com/token"
RETRIABLE_STATUS = {500, 502, 503, 504}
MAX_RETRIES = 5


def _service():
    config.require("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN")
    creds = Credentials(
        token=None,
        refresh_token=config.YT_REFRESH_TOKEN,
        token_uri=TOKEN_URI,
        client_id=config.YT_CLIENT_ID,
        client_secret=config.YT_CLIENT_SECRET,
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def _hashtags(tags, limit=4):
    out = []
    for t in tags or []:
        t = "".join(ch for ch in str(t) if ch.isalnum())
        if t and t.lower() != "shorts" and t not in out:
            out.append(t)
    return " ".join(f"#{t}" for t in out[:limit])


def build_metadata(title, description, tags):
    """Shorts-friendly snippet/status for videos.insert."""
    desc = (description or "").strip()
    extra = "#Shorts " + _hashtags(tags)
    if "#shorts" not in desc.lower():
        desc = f"{desc}\n\n{extra}".strip()
    clean_tags = [str(t).lstrip("#")[:30] for t in (tags or [])][:15]
    return {
        "snippet": {
            "title": (title or "Reddit story").strip()[:100],
            "description": desc[:5000],
            "tags": clean_tags,
            "categoryId": config.YT_CATEGORY_ID,
        },
        "status": {
            "privacyStatus": config.YT_PRIVACY_STATUS,
            "selfDeclaredMadeForKids": False,
            # YouTube's "altered or synthetic content" disclosure; on by default
            # because the stories and narration are AI-generated.
            "containsSyntheticMedia": config.YT_SYNTHETIC_MEDIA,
        },
    }


def upload(video_path, title, description, tags):
    youtube = _service()
    body = build_metadata(title, description, tags)
    media = MediaFileUpload(video_path, chunksize=8 * 1024 * 1024, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response, retries = None, 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                print(f"[upload_youtube] {int(status.progress() * 100)}% uploaded")
        except HttpError as exc:
            if exc.resp.status in RETRIABLE_STATUS and retries < MAX_RETRIES:
                retries += 1
                time.sleep(2 ** retries)
                continue
            raise

    video_id = response["id"]
    print(f"[upload_youtube] published as {body['status']['privacyStatus']}: https://youtube.com/shorts/{video_id}")
    return video_id
