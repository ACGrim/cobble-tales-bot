"""
Daily orchestrator for the Cobble Tales bot. This is the single entrypoint
GitHub Actions runs each day: it builds REDDIT_STORIES_PER_DAY original
Reddit-story videos and posts them to Instagram Reels and/or TikTok.

This is a wholly separate content pipeline from any YouTube channel --
original (not scraped) short stories in the voice of viral "Reddit story"
posts (AITA, TIFU, confession, revenge, etc.), narrated over Minecraft
parkour footage. Nothing here ever touches YouTube.

Each video is fully independent end to end -- pick category -> write story
-> voice it -> build the video -> upload -> record as used.

Each video is attempted in its own try/except so one failure (a flaky API
call, a transient error) doesn't take down the rest of the day's posts.
The run exits non-zero at the end if anything failed, so GitHub Actions
still surfaces it, but only after every video got a shot.

Run locally with:  python -m src.main
"""
import os
import re
import sys
import traceback

from . import (
    config,
    topics,
    generate_reddit_story,
    tts,
    captions,
    assemble_video,
    hosting,
    upload_instagram,
    upload_tiktok,
)


def _hashtags(tags):
    cleaned = (re.sub(r"[^0-9A-Za-z_]", "", str(t)) for t in tags or [])
    return " ".join(f"#{t}" for t in cleaned if t)


def _add_to_run_summary(markdown):
    """Appends to the GitHub Actions run page's summary (no-op locally)."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(markdown + "\n")


def _post_to_reels_and_tiktok(video_path, title, caption, label, duration=None):
    """Uploads a finished video to Instagram Reels and/or TikTok. Never
    raises -- a posting failure here shouldn't take down the rest of the
    run. Skips entirely (silently) if the R2 hosting credentials aren't
    configured, so this is a no-op until SETUP.md has been followed."""
    if not config.CROSSPOST_HOSTING_ENABLED:
        return
    if not (config.IG_CROSSPOST_ENABLED or config.TIKTOK_CROSSPOST_ENABLED):
        return

    try:
        public_url, key = hosting.upload_public(video_path)
    except Exception:
        print(f"[main] {label}: hosting upload FAILED", file=sys.stderr)
        traceback.print_exc()
        return

    if config.IG_CROSSPOST_ENABLED:
        try:
            upload_instagram.upload(public_url, caption)
            print(f"[main] {label}: Instagram Reels SUCCESS")
        except Exception:
            print(f"[main] {label}: Instagram FAILED", file=sys.stderr)
            traceback.print_exc()

    if config.TIKTOK_CROSSPOST_ENABLED:
        try:
            result = upload_tiktok.upload(public_url, title, duration=duration)
            if result["kind"] == "draft":
                print(f"[main] {label}: TikTok draft is in your TikTok inbox -- open the "
                      f"TikTok app to post it (caption is on this run's summary page)")
                # TikTok drafts can't carry a caption, so put it where it's
                # easy to copy from a phone: the Actions run's summary page.
                _add_to_run_summary(
                    f"### TikTok draft ready: {label}\n"
                    f"Open the TikTok app, tap the inbox notification, paste this caption, "
                    f"set **Who can watch** to **Everyone**, and post.\n\n"
                    f"```\n{title}\n```\n")
            else:
                print(f"[main] {label}: TikTok SUCCESS ({result['privacy']})")
        except Exception:
            print(f"[main] {label}: TikTok FAILED", file=sys.stderr)
            traceback.print_exc()

    hosting.delete(key)


def run_reddit_story(index, session_used_categories):
    """Builds and posts one Reddit-story video. Returns the category on
    success (so the caller can mark it used), raises on failure."""
    work_dir = os.path.join(config.WORK_DIR, f"reddit_story_{index}")
    os.makedirs(work_dir, exist_ok=True)

    category, used_before = topics.get_next_topic(
        bank_file=config.REDDIT_STORY_CATEGORIES_FILE,
        used_file=config.USED_REDDIT_STORY_CATEGORIES_FILE,
        extra_used=session_used_categories,
    )
    print(f"[main] Reddit story {index} category: {category}")

    story_data = generate_reddit_story.generate(category)
    print(f"[main] Reddit story {index} title: {story_data['title']}")

    # Title read first (over the Reddit card), then the story.
    narration_path = os.path.join(work_dir, "narration.mp3")
    narration = tts.narrate(story_data["title"], story_data["script"], work_dir, narration_path)
    duration = narration["duration"]

    if (duration < config.REDDIT_STORY_TARGET_SECONDS_MIN - 5
            or duration > config.REDDIT_STORY_TARGET_SECONDS_MAX + 15):
        print(f"[main] WARNING: Reddit story {index} narration is {duration:.1f}s, outside "
              f"target range {config.REDDIT_STORY_TARGET_SECONDS_MIN}-"
              f"{config.REDDIT_STORY_TARGET_SECONDS_MAX}s. Continuing anyway.")

    if narration["words"]:
        caption_events = captions.word_caption_events(narration["words"])
    else:
        print(f"[main] Reddit story {index}: TTS returned no word timings -- "
              f"timing captions proportionally instead.")
        caption_events = captions.proportional_caption_events(
            story_data["script"], narration["body_start"], duration)

    out_path = os.path.join(work_dir, "output.mp4")
    assemble_video.assemble(
        narration_path,
        assemble_video.build_parkour_background,
        caption_events, work_dir, out_path,
        w=config.VIDEO_WIDTH, h=config.VIDEO_HEIGHT,
        story_title=story_data["title"], category=category,
        title_end=narration["body_start"],
    )
    print(f"[main] Reddit story {index} assembled: {out_path}")

    hashtags = _hashtags(story_data.get("tags"))
    ig_caption = "\n\n".join(p for p in (story_data["title"], story_data["description"], hashtags) if p)
    tiktok_caption = " ".join(p for p in (story_data["title"], hashtags) if p)
    _post_to_reels_and_tiktok(out_path, tiktok_caption, ig_caption,
                              label=f"Reddit story {index}", duration=duration)
    print(f"[main] Reddit story {index} done.")

    topics.mark_topic_used(category, used_before, used_file=config.USED_REDDIT_STORY_CATEGORIES_FILE)
    return category


def run():
    os.makedirs(config.WORK_DIR, exist_ok=True)

    if not (config.IG_CROSSPOST_ENABLED or config.TIKTOK_CROSSPOST_ENABLED):
        print("[main] No Instagram/TikTok credentials configured yet -- nothing to do. "
              "See SETUP.md.")
        return

    failures = []
    session_used_story_categories = set()
    for i in range(1, config.REDDIT_STORIES_PER_DAY + 1):
        try:
            category = run_reddit_story(i, session_used_story_categories)
            session_used_story_categories.add(category)
        except Exception:
            print(f"[main] Reddit story {i} FAILED", file=sys.stderr)
            traceback.print_exc()
            failures.append(f"reddit_story_{i}")

    if failures:
        print(f"[main] Run finished with failures: {', '.join(failures)}", file=sys.stderr)
        sys.exit(1)

    print("[main] All videos posted successfully.")


if __name__ == "__main__":
    try:
        run()
    except SystemExit:
        raise
    except Exception:
        print("[main] FAILED (unhandled error before/around per-video runs)", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
