# Cobble Tales — automated daily Reddit-story videos for Instagram Reels, TikTok and YouTube Shorts

A fully automated content pipeline that writes, voices, edits, and posts
**REDDIT_STORIES_PER_DAY original "Reddit story" style videos every day**
to Instagram Reels and TikTok, with no manual work after initial setup.
Runs entirely on GitHub Actions' free cron scheduler — not dependent on
your computer being on, or on any Claude session staying open.

This was split out of the `career-edge-bot` repo (a separate YouTube
Shorts/long-form channel) so the two content pipelines — and their
credentials — are fully independent. This repo now also posts Shorts to its own
Cobble Tales YouTube channel (separate credentials from career-edge-bot),
and nothing in `career-edge-bot` touches Instagram/TikTok.

**Format:** original (not scraped) short stories written in the voice and
conventions of viral "Reddit story" posts (AITA, TIFU, confession,
relationship, petty revenge, creepy encounter, etc.), narrated over a
continuous clip of **Pip**, the channel's blocky mascot, running an obstacle
course (original animation; Minecraft parkour is still available) — see `src/generate_reddit_story.py`
for why these are AI-original rather than real scraped Reddit posts (short
version: Reddit's API is now practically closed to small projects), and
`tools/blocky_background/README.md` for how the background clips are made.

## How a day's videos get made (fully automatic)

1. **Category** — pulled from `data/reddit_story_categories.json`, a
   rotating bank of story genres/prompts. `data/used_reddit_story_categories.json`
   tracks what's already run so nothing repeats until the bank cycles.
2. **Story** — Claude (Anthropic API) writes an original ~140-220 word
   story in the genre's voice, with a title, hook, captions, description,
   and hashtags.
3. **Voice** — narrated with a consistent neural TTS voice (`edge-tts`,
   free), giving the channel a recognizable "host."
4. **Background** — one continuous clip, picked by `BACKGROUND_STYLE`:
   `blocky` (default) uses Pip's obstacle-course clips from `assets/blocky/`,
   `parkour` uses Minecraft parkour from `assets/parkour/`, `mix` picks from
   both. Cropped to fill the vertical frame (falls back to the other folder, then to a
   plain gradient if that folder is empty).
5. **Assembly** — `moviepy` + `Pillow` composite the background, burned-in
   branded captions, and a quiet background music bed into a finished
   1080x1920 MP4.
6. **Hosting** — the finished video is temporarily uploaded to Cloudflare
   R2 (S3-compatible object storage) so Instagram/TikTok's servers have a
   URL to fetch it from, then deleted once posted.
7. **Upload** — posted to Instagram Reels (Graph API) and/or TikTok
   (Content Posting API), whichever credentials are configured. Each
   platform's post is wrapped in its own try/except so one platform
   failing never blocks the other or the rest of the day's videos.
8. **TikTok token refresh** — runs automatically before the main pipeline
   every day (`scripts/refresh_tiktok_token.py`), since TikTok access
   tokens expire in ~24h. See SETUP.md Part 5.
9. **State** — the used category is committed back to the repo so
   tomorrow's run picks something new.

## Repo layout

```
src/
  main.py                  orchestrates the full daily run
  generate_reddit_story.py Claude story generation
  tts.py                   edge-tts narration
  captions.py              timing captions to narration length
  assemble_video.py        moviepy/Pillow video assembly (blocky or parkour background)
  hosting.py               Cloudflare R2 temporary public hosting
  upload_instagram.py      Instagram Graph API Reels publish
  upload_tiktok.py         TikTok Content Posting API publish
  upload_youtube.py        YouTube Data API upload as a Short
  topics.py                category rotation bookkeeping
  config.py                central env-var config
scripts/
  refresh_tiktok_token.py  runs before each daily post; keeps the TikTok
                           access token fresh with zero manual steps
data/
  reddit_story_categories.json       story genre/prompt bank
  used_reddit_story_categories.json  rotation state (auto-updated by CI)
assets/
  music/     royalty-free background tracks
  blocky/    Pip obstacle-course background clips (rendered by
             tools/blocky_background/render_clips.py)
  parkour/   Minecraft parkour gameplay clips (you provide these — empty
             by default; see assets/parkour/README.txt)
tools/
  blocky_background/  the animated course (course.html) and the script that
                      renders it to MP4 clips
.github/workflows/daily.yml   the cron job that runs everything, daily
```

## Setup

**Start with SETUP.md** — it walks through the one-time account/credential
setup (Anthropic, Cloudflare R2, Instagram Graph API, TikTok Content
Posting API, and the TikTok auto-refresh secrets) step by step.

## Local testing

```
pip install -r requirements.txt
cp .env.example .env   # fill in real values
export $(cat .env | xargs)   # or use python-dotenv
python -m src.main
```

Set `REDDIT_STORIES_PER_DAY` (default 3) to change how many stories run
per day. TikTok posts go out public (`TIKTOK_PRIVACY_LEVEL` in
`.github/workflows/daily.yml`); if TikTok ever refuses a public post,
`TIKTOK_FALLBACK` sends the video to your TikTok inbox (`inbox`, default) or
posts it privately (`private`) so it still goes up.
Narration uses two natural-sounding voices, Andrew for male narrators and Ava
for female ones (`TTS_VOICE_MALE` / `TTS_VOICE_FEMALE`, or force one with
`TTS_VOICE`); each story says which its narrator is.
`BACKGROUND_STYLE` picks the background (`blocky`, `parkour` or `mix`; in
GitHub Actions set it as a repo Variable). `TIKTOK_IS_AIGC` (default `true`)
ticks TikTok's "AI-generated content" label on each post, since the stories
are AI-written.

## Follow call-to-action

Every video ends with the narrator saying `FOLLOW_CTA_LINE` ("Follow Cobble
Tales for a new story every day.") while a follow card pops up: Pip's
avatar, the channel name, `FOLLOW_CTA_SUBTITLE` and a Follow button that
flips to Following. Set `FOLLOW_CTA=false` to turn it off.

## Checking tokens

If a run logs a token warning, open the Actions tab and run **Check tokens**.
It posts nothing; it tests `GH_SECRETS_PAT`, the TikTok refresh and the
Instagram token + refresh, and prints each service's exact error.

## Realistic expectations

TikTok will only accept private posts (visible to nobody but you) until
TikTok manually audits your developer app — that's TikTok's own review
process, entirely out of this pipeline's control, with no guaranteed
turnaround. Instagram has no equivalent review step for your own account.
The default blocky background is original animation made for this channel,
so there's no third-party footage license to worry about. If you switch to
`parkour`, see `assets/parkour/README.txt` for where to safely source clips
you can monetize. If neither folder has clips, videos still build with a
plain gradient background.
