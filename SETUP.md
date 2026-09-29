# Setup: Cobble Tales (Instagram Reels + TikTok Reddit-story bot)

This is the one-time account/credential setup for this pipeline.
**REDDIT_STORIES_PER_DAY Reddit-story videos, Instagram/TikTok only.**
Original (not scraped) short stories written in the voice/genre of viral
"Reddit story" posts (AITA, TIFU, confession, etc.), narrated over a
continuous parkour gameplay shot. See `src/generate_reddit_story.py` for why
these are AI-original rather than real scraped Reddit posts (short version:
Reddit's API is now practically closed to small projects). Background
gameplay needs no setup: it's generated automatically unless you add your
own clips (see "Optional: use your own gameplay footage" at the end).

Everything below is required before the daily workflow does anything --
until Parts 1-4 are done, `python -m src.main` just prints that no
credentials are configured and exits cleanly.

**Read this first:** TikTok won't let an app publish public posts on its
own until TikTok manually audits your developer app. That audit is
TikTok's own review process, entirely out of this pipeline's control, and
there's no guarantee of a fast turnaround or approval for a new/automated
account. Start the audit early (Part 3 below) since the queue takes time
regardless. Until it's approved you can still have a public account with
public videos: each video is sent to your TikTok inbox as a draft and you
post it with one tap (Part 6). Instagram has no equivalent review step for
your own account.

You'll also need an `ANTHROPIC_API_KEY` (from console.anthropic.com) for
the story-writing step -- same idea as any other Claude API key.

---

## Part 1: Cloudflare R2 (video hosting)

Instagram and TikTok's publish APIs both work by having *their* servers
fetch your video from a URL you give them -- neither accepts a direct file
upload the way YouTube's API does. R2 is free object storage used to give
them that URL.

1. Go to [dash.cloudflare.com](https://dash.cloudflare.com) and sign up
   (free) if you don't have an account.
2. In the left sidebar, go to **R2 Object Storage** → **Create bucket**.
   Name it e.g. `cobble-tales-media`. Location: Automatic.
3. Open the new bucket → **Settings** tab → **Public access** → enable
   **R2.dev subdomain access**. Copy the public URL it gives you (looks
   like `https://pub-xxxxxxxx.r2.dev`) -- that's your `R2_PUBLIC_BASE_URL`.
4. Same Settings tab → **Object lifecycle rules** → add a rule that
   expires objects after 1 day. This is just a backstop, in case a run
   crashes right after uploading and never gets to delete it itself.
5. Go to **R2 → Overview → Manage API tokens** (top right) → **Create API
   token**. Permissions: **Object Read & Write**, scoped to your bucket.
   Create it, then copy the three values it shows you *once*:
   - Access Key ID → `R2_ACCESS_KEY_ID`
   - Secret Access Key → `R2_SECRET_ACCESS_KEY`
   - The Account ID shown on the R2 Overview page → `R2_ACCOUNT_ID`
6. `R2_BUCKET_NAME` is just the bucket name from step 2 (`cobble-tales-media`).

---

## Part 2: Instagram Reels

**Requires:** an Instagram account converted to a Professional (Business
or Creator) account, linked to a Facebook Page.

1. In the Instagram app: **Settings → Account type and tools → Switch to
   professional account**, pick Business or Creator, follow the prompts.
2. During that flow (or afterwards under **Settings → Account Center →
   Sharing across profiles**), link it to a Facebook Page. If you don't
   have one, Instagram will offer to create one for you automatically --
   that's fine, it doesn't need to be a "real" active Page.
3. Go to [developers.facebook.com](https://developers.facebook.com) → **My
   Apps → Create App**. Choose the "Other" use case → app type
   **Business**. Give it any name (e.g. "Cobble Tales Poster").
4. In the app dashboard, **Add Product** → find **Instagram** → set up
   the **Instagram API with Instagram Login** or **Instagram Graph API**
   product (Meta's product naming shifts periodically -- pick whichever
   one lists `instagram_content_publish` among its permissions).
5. Under the app's **Roles** settings, add your own Facebook/Instagram
   account as an **Instagram Tester** (or Admin). This is the step that
   lets your own account use the API in development mode *without* Meta's
   full App Review process -- App Review is only needed for other
   people's accounts.
6. Accept the tester invite (there's a prompt inside the Instagram app
   itself, under Settings → Apps and websites, or via the link Meta emails).
7. Use Meta's **Graph API Explorer**
   ([developers.facebook.com/tools/explorer](https://developers.facebook.com/tools/explorer)):
   select your app, select your Page, generate a **User Access Token**
   with `instagram_basic`, `instagram_content_publish`, and
   `pages_read_engagement` permissions.
8. Exchange that short-lived token for a **long-lived token** (60 days) by
   calling:
   ```
   GET https://graph.facebook.com/v21.0/oauth/access_token
     ?grant_type=fb_exchange_token
     &client_id=<your app id>
     &client_secret=<your app secret>
     &fb_exchange_token=<short-lived token from step 7>
   ```
   That long-lived token is your `IG_ACCESS_TOKEN`. (It expires every 60
   days -- refresh it the same way before it does, or look into a System
   User token for something that doesn't expire, if this becomes annoying.)
9. Find your Instagram professional account's numeric ID: `GET
   https://graph.facebook.com/v21.0/me/accounts?access_token=<token>` to
   get your Page ID, then `GET
   https://graph.facebook.com/v21.0/<page id>?fields=instagram_business_account&access_token=<token>`.
   The number that comes back is `IG_USER_ID`.

---

## Part 3: TikTok (start the audit early)

1. Go to [developers.tiktok.com](https://developers.tiktok.com) → sign up
   → **Manage apps → Create an app**.
2. Add the **Content Posting API** product, and request both the
   `video.publish` (Direct Post) and `video.upload` (send drafts to your
   inbox) scopes -- Part 6 explains why both.
3. Fill in and submit the **audit/review** request as soon as the app is
   created -- this is the queue that takes time, so starting it now (even
   before you have videos to show) is worth it. TikTok will ask what the
   app does; describe it honestly as automated posting of original,
   Claude-written short stories (in the style of viral "Reddit story"
   posts, over gameplay footage) for your own TikTok account.
4. This app also needs a verified redirect domain (Login Kit) and, for
   posting videos hosted via a URL, a **separate URL-ownership
   verification** for the domain your videos will be hosted from
   (`R2_PUBLIC_BASE_URL` from Part 1) -- see
   [developers.tiktok.com/doc/content-posting-api-media-transfer-guide/#pull_from_url](https://developers.tiktok.com/doc/content-posting-api-media-transfer-guide/#pull_from_url).
   This is a distinct check from the redirect_uri/Login Kit domain
   verification and TikTok will reject every post with
   `url_ownership_unverified` until it's done. Follow TikTok's own
   in-dashboard instructions for verifying that domain (usually a meta tag
   or a `tiktok-developers-site-verification=...` file served from it).
5. While waiting on the audit, complete the OAuth flow to get a token
   anyway: `scripts/authorize_tiktok.py` walks through it (Part 6 step 3
   has the exact commands) -- you'll end up with a refresh_token tied to
   your TikTok account, which Part 5 needs.
6. Nothing to flip when the audit passes: posts are public by default, and
   the pipeline switches from inbox drafts to fully automatic public posts
   on its own (Part 6).

---

## Part 4: add everything as GitHub repo Secrets

Repo → **Settings → Secrets and variables → Actions → New repository
secret**, one for each of:

```
ANTHROPIC_API_KEY
R2_ACCOUNT_ID
R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY
R2_BUCKET_NAME
R2_PUBLIC_BASE_URL
IG_ACCESS_TOKEN
IG_USER_ID
```

`TIKTOK_ACCESS_TOKEN` is set automatically by Part 5's refresh step below
rather than as a static secret -- do Part 5 before your first real run so
TikTok posting works at all.

The pipeline checks for these at runtime and silently skips the run
entirely until they're all set, so there's no rush and nothing breaks in
the meantime -- add Instagram's first since it doesn't need an audit, then
TikTok's once Part 5 is done.

## Testing

Once the Instagram secrets are set, trigger a manual run
(`workflow_dispatch`) and watch the Actions log for `[upload_instagram]`
lines to confirm the container gets created, processed, and published, and
`[main] Reddit story` lines to confirm those built and posted too. An
`[assemble] background:` line says which gameplay each video used --
"generated block-parkour gameplay" is expected until you add real clips.

---

## Part 5: TikTok token auto-refresh (one-time setup, required)

TikTok access tokens expire in ~24h, so without this part TikTok posting
quietly stops working about a day after you first set it up. This is
required, not optional, for TikTok to work on an unattended schedule:
once it's done, TikTok stays working indefinitely with zero further action
from you. There's a `Refresh TikTok access token` step in `daily.yml` and a
`scripts/refresh_tiktok_token.py` that already do this automatically --
this part is just adding the four secrets it needs.

**Why Instagram doesn't have this problem, or at least not this badly:**
Instagram's access token is a long-lived type (~60 days, and the pipeline
doesn't currently auto-refresh it either, so mark your calendar or redo
Part 2 every couple months). TikTok's refresh tokens are rotated
(invalidated and replaced) on every single use, which is what
`scripts/refresh_tiktok_token.py` handles by writing the new one back to
GitHub every day.

### 5a. Get your TikTok app's Client Key and Client Secret

developers.tiktok.com → your app (the **Sandbox** app if that's what you
used in Part 3) → the Client Key is shown directly; click the eye icon
next to Client Secret to reveal it. Copy both -- you'll paste the secret
into GitHub in step 5c, never anywhere else.

### 5b. Get a refresh_token (redo the OAuth authorize step from Part 3 if needed)

If you didn't save the `refresh_token` from Part 3 step 5, run the
authorize → exchange flow with `scripts/authorize_tiktok.py` (exact
commands in Part 6 step 3). It prints the `TIKTOK_REFRESH_TOKEN` value you
need here, and asks TikTok for the draft permission (`video.upload`) at
the same time.

### 5c. Create a scoped GitHub token so the workflow can update its own secrets

The refresh script needs permission to write new secret values back to
this repo (GitHub's default `GITHUB_TOKEN` inside Actions can't do this --
secret management needs a personal token). To keep this as low-risk as
possible, create a **fine-grained** token scoped to only this repo with
only the one permission it needs:

1. github.com → Settings (your account, not the repo) → Developer settings
   → Personal access tokens → Fine-grained tokens → Generate new token.
2. Resource owner: your account. Repository access: **Only select
   repositories** → this repo (`cobble-tales-bot`).
3. Permissions → Repository permissions → **Secrets** → **Read and
   write**. Leave every other permission at "No access."
4. Set an expiration (GitHub caps fine-grained tokens at 1 year; set a
   calendar reminder to regenerate it before then, or it'll silently stop
   working and TikTok refresh will go quiet again).
5. Generate, and copy the token immediately -- GitHub only shows it once.

### 5d. Add the four new secrets

Repo → Settings → Secrets and variables → Actions → New repository
secret, one for each of:

```
TIKTOK_CLIENT_KEY
TIKTOK_CLIENT_SECRET
TIKTOK_REFRESH_TOKEN
GH_SECRETS_PAT       (the fine-grained token from 5c)
```

That's it -- the next scheduled or manual run will refresh the token
before posting anything, and silently keep doing that forever. If it ever
stops working (token revoked, PAT expired), the pipeline just skips
TikTok posting and keeps posting to Instagram; check the `Refresh TikTok
access token` step's log for a `[refresh_tiktok_token]` line explaining
why.

---

## Part 6: Public TikTok posts

What TikTok allows (their rules -- nothing in code can get around them):

- **Before the audit passes**, an app can only Direct Post while your
  TikTok account is **private**, and those posts are "only me". If the
  account is public, TikTok rejects the post. What an unaudited app *can*
  do is send the video to your TikTok **inbox as a draft**: you get a
  notification, tap it, and post it publicly yourself.
- **After the audit passes**, the app can post publicly by itself.

The pipeline handles both automatically (`TIKTOK_POST_MODE=auto`, the
default): it tries a public post first, and if TikTok says the app isn't
audited yet it sends that day's videos to your inbox as drafts instead.
The day the audit passes, posts start going up publicly on their own --
nothing to change.

One-time setup:

1. **Make the TikTok account public:** TikTok app → Profile → ☰ →
   Settings and privacy → Privacy → turn **Private account** off.
2. **Give the app the draft permission:** developers.tiktok.com → your app
   → Content Posting API → make sure the upload/draft permission
   (`video.upload`) is enabled alongside Direct Post (`video.publish`).
   Portal wording shifts; the scopes list should show both.
3. **Re-authorize so the login includes it** (a token only has the
   permissions it was approved with). On your computer, in this repo:
   ```
   python3 scripts/authorize_tiktok.py url --client-key <CLIENT_KEY> --redirect-uri <REDIRECT_URI>
   ```
   Use the Client Key from your app page and *exactly* the Redirect URI
   registered under the app's Login Kit settings. Open the printed link
   while logged into the bot's TikTok account and approve. Your callback
   page shows a `code`; within a few minutes run:
   ```
   python3 scripts/authorize_tiktok.py exchange <CODE> --client-key <CLIENT_KEY> --redirect-uri <REDIRECT_URI>
   ```
   Paste the client secret when asked, then save the printed value as the
   `TIKTOK_REFRESH_TOKEN` repo secret (replacing the old one). The next
   run's `Refresh TikTok access token` step logs the permissions -- it
   should list `video.upload`.
4. If you ever created a `TIKTOK_PRIVACY_LEVEL` repo variable set to
   `SELF_ONLY`, delete it (or set it to `PUBLIC_TO_EVERYONE`).

**Posting a draft (until the audit passes):** after each run, open the
TikTok app → inbox notification → the video opens in the editor. TikTok
doesn't let apps pre-fill a draft's caption, so the run page on GitHub
(Actions → the run → **Summary**) lists each video's caption with its
hashtags, ready to copy. Paste it, set **Who can watch** to **Everyone**,
and post. TikTok caps how many unposted drafts can pile up (5 per 24
hours), so post or delete them each day -- 3 videos a day fits.

`TIKTOK_POST_MODE` (repo variable) can also be `draft` (always send drafts,
even after the audit) or `direct` (never fall back to drafts).

---

## Optional: use your own gameplay footage

Nothing to do here unless you want real recorded gameplay instead of the
generated block-parkour course every video gets by default. Two ways:

1. **Small clips (under 100MB each):** commit them to `assets/parkour/`.
   See `assets/parkour/README.txt` for where to get footage you're allowed
   to monetize.
2. **Big clips:** host them anywhere with a direct download link -- e.g. a
   *second* R2 bucket (created the same way as Part 1 steps 2-3, with public
   access on but **no** expiry rule; the Part 1 bucket's 1-day rule would
   delete them). Then add a repo **Variable** (Settings → Secrets and
   variables → Actions → **Variables** tab) named `PARKOUR_CLIP_URLS` with
   the links, separated by commas or spaces, e.g.
   `https://pub-yyyyyyyy.r2.dev/parkour1.mp4, https://pub-yyyyyyyy.r2.dev/parkour2.mp4`.
   They're downloaded at the start of each run.

Clips in `assets/parkour/` win over `PARKOUR_CLIP_URLS`; if a clip can't be
opened or downloaded, that video falls back to generated gameplay instead of
failing.
