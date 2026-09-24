"""
Temporary public video hosting via Cloudflare R2 (S3-compatible object
storage). Instagram and TikTok's publish APIs both work by having THEIR
servers fetch the video from a URL you give them -- neither accepts a
direct file upload the way YouTube's resumable-upload API does. This
module uploads the finished Short there and hands back a public URL, then
deletes it again once every platform has had a chance to fetch it.

Set a lifecycle rule on the R2 bucket (once, in the Cloudflare dashboard)
to auto-expire objects after a day, as a backstop in case delete() is
never reached (e.g. the run crashes right after uploading).
"""
import uuid

import boto3
from botocore.config import Config as BotoConfig

from . import config


def _client():
    config.require("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY")
    endpoint = f"https://{config.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=config.R2_ACCESS_KEY_ID,
        aws_secret_access_key=config.R2_SECRET_ACCESS_KEY,
        config=BotoConfig(signature_version="s3v4"),
        region_name="auto",
    )


def upload_public(local_path, key=None):
    """Uploads local_path to the R2 bucket and returns (public_url, key).
    Keys are randomized so concurrent/same-day runs never collide."""
    config.require("R2_BUCKET_NAME", "R2_PUBLIC_BASE_URL")
    if key is None:
        key = f"{uuid.uuid4().hex}.mp4"

    client = _client()
    client.upload_file(
        local_path,
        config.R2_BUCKET_NAME,
        key,
        ExtraArgs={"ContentType": "video/mp4"},
    )

    base = config.R2_PUBLIC_BASE_URL.rstrip("/")
    public_url = f"{base}/{key}"
    print(f"[hosting] uploaded {local_path} -> {public_url}")
    return public_url, key


def delete(key):
    """Best-effort cleanup. Never raises -- a failed delete just means the
    lifecycle rule cleans it up later instead."""
    try:
        client = _client()
        client.delete_object(Bucket=config.R2_BUCKET_NAME, Key=key)
        print(f"[hosting] deleted {key}")
    except Exception as e:
        print(f"[hosting] WARNING: failed to delete {key}: {e}")
