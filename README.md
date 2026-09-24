# Cobble Tales — automated daily Reddit-story videos for Instagram Reels + TikTok

A fully automated content pipeline that writes, voices, edits, and posts
**REDDIT_STORIES_PER_DAY original "Reddit story" style videos every day**
to Instagram Reels and TikTok, with no manual work after initial setup.
Runs entirely on GitHub Actions' free cron scheduler — not dependent on
your computer being on, or on any Claude session staying open.

This was split out of the `career-edge-bot` repo (a separate YouTube
Shorts/long-form channel) so the two content pipelines — and their
credentials — are fully independent. Nothing here ever touches YouTube,
and nothing in `career-edge-bot` touches Instagram/TikTok.

**Format:** original (not scraped) short stories written in the voice and
conventions of viral "Reddit story" posts (AITA, TIFU, confession,
relationship, petty revenge, creepy encounter, etc.), narrated over a
continuous Minecraft parkour gameplay clip — see `src/generate_reddit_story.py`
for why these are AI-original rather than real scraped Reddit posts (short
version: Reddit's API is now practically closed to small projects), and
`assets/parkour/README.txt` for how to source the background footage.

## How a day's videos get made (fully automatic)

1. **Category** — pulled from `data/reddit_story_categories.json`, a
   rotating bank of story genres/prompts. `data/used_reddit_story_categories.json`
   tracks what's already run so nothing repeats until the bank cycles.
2. **Story** — Claude (Anthropic API) writes an original ~140-220 word
   story in the genre's voice, with a title, hook, captions, description,
   and hashtags.
3. **Voice** — narrated with a consistent neural TTS voice (`edge-tts`,
   free), giving the channel a recognizable "host."
4. **Background** — one continuous Minecraft parkour clip from
   `assets/parkour/`, cropped to fill the vertical frame (falls back to a
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
  assemble_video.py        moviepy/Pillow video assembly (parkour background)
  hosting.py               Cloudflare R2 temporary public hosting
  upload_instagram.py      Instagram Graph API Reels publish
  upload_tiktok.py         TikTok Content Posting API publish
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
  parkour/   Minecraft parkour gameplay clips (you provide these — empty
             by default; see assets/parkour/README.txt)
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
per day. `TIKTOK_PRIVACY_LEVEL` controls TikTok visibility (stays
`SELF_ONLY` until TikTok approves the app — see SETUP.md).

## Realistic expectations

TikTok will only accept private posts (visible to nobody but you) until
TikTok manually audits your developer app — that's TikTok's own review
process, entirely out of this pipeline's control, with no guaranteed
turnaround. Instagram has no equivalent review step for your own account.
If `assets/parkour/` is empty, videos still build fine with a plain
gradient background instead of real gameplay footage — see that folder's
README for where to safely source clips you can monetize.
