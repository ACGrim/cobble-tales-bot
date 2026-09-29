"""
Assembles the final vertical (1080x1920) Reddit-story video from:
  - narration audio (mp3, from tts.py): the post title, then the story
  - full-screen parkour gameplay: a real clip from assets/parkour/ (or
    PARKOUR_CLIP_URLS) cover-cropped to fill the frame, or freshly generated
    block-parkour gameplay from gameplay.py when there's no real footage
  - a mock Reddit post card (subreddit/title/fake votes) centered on screen
    while the title is read, so it reads like a screenshot of the post
  - big word-by-word captions synced to the narration, with the word being
    spoken highlighted (rendered with Pillow, NOT ImageMagick, so this runs
    cleanly on a stock GitHub Actions runner with no extra system config)
  - an optional looped background music bed from assets/music/
  - a small static brand wordmark bar

Deliberately avoids moviepy's TextClip (which shells out to ImageMagick and
needs a policy.xml patch to allow text rendering) in favor of Pillow-rendered
PNG overlays — one less fragile moving part in CI.
"""
import glob
import hashlib
import os
import random
import sys
import traceback
from urllib.parse import urlparse

import requests

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# Pillow >=10 removed Image.ANTIALIAS; moviepy 1.0.3's resize still
# references it, so shim it back in for compatibility.
if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.LANCZOS
from moviepy.editor import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    VideoFileClip,
)
from moviepy.audio.fx.all import audio_loop, volumex
from moviepy.video.fx.all import crop
from moviepy.video.fx.all import loop as loop_video

from . import config, gameplay

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]


def _load_font(size):
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _wrap_text(draw, text, font, max_width):
    words = text.split()
    lines, current = [], ""
    for w in words:
        trial = (current + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines


# Big word-by-word captions, the genre's look: 1-3 words at a time, heavy
# uppercase type with a thick black outline (legible over any footage without
# a background box), and the word being spoken right now in yellow.
CAPTION_FONT_SIZE = 86
CAPTION_CENTER_Y = 0.5  # vertical center of the caption, as a fraction of frame height
CAPTION_COLOR = (255, 255, 255, 255)
CAPTION_HIGHLIGHT = (255, 224, 46, 255)


def _load_caption_font(size):
    if os.path.exists(config.CAPTION_FONT):
        return ImageFont.truetype(config.CAPTION_FONT, size)
    return _load_font(size)


def _render_caption_png(words, active, out_path, w=config.VIDEO_WIDTH, font_size=CAPTION_FONT_SIZE):
    """Renders one caption chunk (list of words, words[active] highlighted;
    active=None highlights nothing) and returns the PNG's (width, height).

    moviepy's ImageClip decodes and holds the FULL image in memory for as long
    as the clip object exists, and a video has one of these per spoken word,
    so the PNG is cropped tight to the text rather than frame-sized."""
    words = [wd.upper() for wd in words] or [""]
    tmp = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    max_w = w - 120
    font = _load_caption_font(font_size)
    # One very long word shouldn't run off the frame: shrink until it fits.
    while font_size > 40 and max(tmp.textlength(wd, font=font) for wd in words) > max_w:
        font_size -= 6
        font = _load_caption_font(font_size)
    stroke = max(5, font_size // 9)
    # The thick outline eats into the font's (narrow) space, so widen it.
    space = tmp.textlength(" ", font=font) + stroke
    widths = [tmp.textlength(wd, font=font) for wd in words]

    lines, cur, cur_w = [], [], 0.0
    for i, ww in enumerate(widths):
        trial = ww if not cur else cur_w + space + ww
        if cur and trial > max_w:
            lines.append((cur, cur_w))
            cur, cur_w = [i], ww
        else:
            cur.append(i)
            cur_w = trial
    lines.append((cur, cur_w))

    ascent, descent = font.getmetrics()
    line_h, line_gap = ascent + descent, 6
    shadow_dy = max(4, font_size // 16)
    pad = stroke + 14
    box_w = int(max(lw for _, lw in lines)) + pad * 2
    box_h = line_h * len(lines) + line_gap * (len(lines) - 1) + pad * 2 + shadow_dy

    def draw_words(draw, dy, shadow):
        y = pad + dy
        for idxs, lw in lines:
            x = (box_w - lw) / 2
            for i in idxs:
                if shadow:
                    fill = stroke_fill = (0, 0, 0, 150)
                else:
                    fill = CAPTION_HIGHLIGHT if i == active else CAPTION_COLOR
                    stroke_fill = (0, 0, 0, 255)
                draw.text((x, y), words[i], font=font, fill=fill,
                          stroke_width=stroke, stroke_fill=stroke_fill)
                x += widths[i] + space
            y += line_h + line_gap

    # Soft drop shadow under the outline, so white text never gets lost on
    # bright sky/quartz/sand.
    shadow = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    draw_words(ImageDraw.Draw(shadow), shadow_dy, shadow=True)
    img = shadow.filter(ImageFilter.GaussianBlur(4))
    draw_words(ImageDraw.Draw(img), 0, shadow=False)
    img.save(out_path)
    return img.size


def _render_brand_bar(out_path, w=config.VIDEO_WIDTH, height=140):
    img = Image.new("RGBA", (w, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = _load_font(46)
    text = config.CHANNEL_BRAND.upper()
    tw = draw.textlength(text, font=font)
    pad_x, pad_y = 30, 16
    left = (w - tw) / 2 - pad_x
    right = (w + tw) / 2 + pad_x
    draw.rounded_rectangle([left, 20, right, 20 + 46 + pad_y * 2], radius=30, fill=(0, 0, 0, 150))
    draw.text(((w - tw) / 2, 20 + pad_y), text, font=font, fill=(255, 255, 255, 255))
    img.save(out_path)
    return out_path


# --- Mock Reddit post card -------------------------------------------------
# Purely original artwork: generic circle "avatar", hand-drawn upvote
# triangle and comment-bubble icons, laid out in Reddit's familiar light
# post-card convention and accent color. No Reddit logo/mascot asset is
# used anywhere -- that's copyrighted/trademarked and isn't ours to embed.
# The subreddit/username/vote counts are cosmetic flavor (this channel
# writes wholly original stories -- see generate_reddit_story.py), not a
# claim that a specific real post exists.

_SUBREDDIT_KEYWORDS = [
    ("aita", "AmItheAsshole"),
    ("tifu", "tifu"),
    ("malicious", "MaliciousCompliance"),
    ("petty-revenge", "pettyrevenge"),
    ("petty revenge", "pettyrevenge"),
    ("creepy", "creepyencounters"),
    ("wholesome", "MadeMeSmile"),
    ("relationship", "relationship_advice"),
    ("family secret", "confession"),
    ("roommate", "AmItheAsshole"),
    ("stranger", "MadeMeSmile"),
    ("bully", "pettyrevenge"),
    ("first job", "antiwork"),
    ("customer service", "talesfromretail"),
    ("workplace", "antiwork"),
    ("confession", "confession"),
]

_USERNAME_ADJECTIVES = [
    "tired", "quiet", "salty", "random", "calm", "tiny", "lucky", "broke",
    "sleepy", "curious", "grumpy", "gentle",
]
_USERNAME_NOUNS = [
    "teacher", "raccoon", "potato", "ghost", "otter", "gremlin", "wanderer",
    "squirrel", "hamster", "nomad", "barista", "intern",
]


def guess_subreddit(category, title):
    text = f"{category or ''} {title or ''}".lower()
    for kw, sub in _SUBREDDIT_KEYWORDS:
        if kw in text:
            return sub
    return "stories"


def _fake_reddit_meta():
    username = (
        f"u/{random.choice(_USERNAME_ADJECTIVES)}_"
        f"{random.choice(_USERNAME_NOUNS)}{random.randint(1, 999)}"
    )
    age = random.choice(
        ["3 hr. ago", "6 hr. ago", "9 hr. ago", "14 hr. ago", "1 d. ago", "2 d. ago"]
    )
    upvotes = random.randint(1200, 48000)
    comments = random.randint(80, 2400)
    return username, age, upvotes, comments


def _format_count(n):
    if n >= 1000:
        v = n / 1000
        return f"{v:.1f}K" if v < 10 else f"{v:.0f}K"
    return str(n)


def _render_reddit_card_png(title, category, out_path, w=config.VIDEO_WIDTH):
    """Renders a mock Reddit post header (subreddit, fake username/age, the
    story's title, fake vote/comment counts) -- the "screenshot of the post"
    viewers expect on screen while the title is read out."""
    subreddit = guess_subreddit(category, title)
    username, age, upvotes, comments = _fake_reddit_meta()

    pad_x, pad_y = 38, 32
    margin = 48  # card's outer margin from the frame edges
    card_w = w - margin * 2
    avatar_d = 66

    header_font = _load_font(34)
    meta_font = _load_font(27)
    title_font = _load_font(47)
    stat_font = _load_font(31)

    tmp_draw = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    max_text_w = card_w - pad_x * 2
    title_lines = _wrap_text(tmp_draw, title, title_font, max_text_w)[:4]

    title_line_h = title_font.size + 12
    title_block_h = title_line_h * len(title_lines)
    gap = 20
    stats_h = 44

    card_h = pad_y * 2 + avatar_d + gap + title_block_h + gap + stats_h
    canvas_h = card_h + 20

    img = Image.new("RGBA", (w, canvas_h), (0, 0, 0, 0))
    card_left, card_top = margin, 0
    card_right, card_bottom = w - margin, card_h

    # Soft drop shadow, baked once into this static PNG (not per-frame).
    shadow = Image.new("RGBA", (w, canvas_h), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        [card_left, card_top + 6, card_right, card_bottom + 6],
        radius=26, fill=(0, 0, 0, 90),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(8))
    img = Image.alpha_composite(img, shadow)
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle(
        [card_left, card_top, card_right, card_bottom],
        radius=26, fill=(255, 255, 255, 240),
    )

    # Generic avatar: solid circle + simple head-and-shoulders silhouette --
    # deliberately NOT Reddit's Snoo mascot.
    ax, ay = card_left + pad_x, card_top + pad_y
    draw.ellipse([ax, ay, ax + avatar_d, ay + avatar_d], fill=(255, 69, 0, 255))
    draw.ellipse(
        [ax + avatar_d * 0.30, ay + avatar_d * 0.20, ax + avatar_d * 0.70, ay + avatar_d * 0.56],
        fill=(255, 255, 255, 255),
    )
    draw.pieslice(
        [ax + avatar_d * 0.10, ay + avatar_d * 0.52, ax + avatar_d * 0.90, ay + avatar_d * 1.20],
        180, 360, fill=(255, 255, 255, 255),
    )

    tx = ax + avatar_d + 18
    draw.text((tx, ay - 2), f"r/{subreddit}", font=header_font, fill=(20, 20, 20, 255))
    draw.text(
        (tx, ay + header_font.size + 4), f"{username} · {age}",
        font=meta_font, fill=(120, 120, 120, 255),
    )

    ty = card_top + pad_y + avatar_d + gap
    for ln in title_lines:
        draw.text((card_left + pad_x, ty), ln, font=title_font, fill=(20, 20, 20, 255))
        ty += title_line_h

    sy = ty + gap
    sx = card_left + pad_x
    # Upvote triangle + count.
    draw.polygon([(sx, sy + 26), (sx + 13, sy), (sx + 26, sy + 26)], fill=(255, 69, 0, 255))
    up_text = _format_count(upvotes)
    draw.text((sx + 36, sy + 2), up_text, font=stat_font, fill=(60, 60, 60, 255))

    # Comment-bubble icon (rounded rect + tail) + count.
    cx = sx + 36 + draw.textlength(up_text, font=stat_font) + 44
    draw.rounded_rectangle([cx, sy - 2, cx + 30, sy + 20], radius=8, fill=(120, 120, 120, 255))
    draw.polygon([(cx + 4, sy + 18), (cx + 4, sy + 27), (cx + 13, sy + 18)], fill=(120, 120, 120, 255))
    draw.text((cx + 42, sy + 2), _format_count(comments), font=stat_font, fill=(60, 60, 60, 255))

    img.save(out_path)
    return out_path


def _gradient_fallback_image(out_path, w=config.VIDEO_WIDTH, h=config.VIDEO_HEIGHT):
    top = (17, 24, 39)
    bottom = (30, 58, 95)
    img = Image.new("RGB", (w, h))
    for y in range(h):
        t = y / h
        row = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        for x in range(0, w, 4):  # step by 4 columns, then stretch — cheap gradient
            img.putpixel((x, y), row)
    img = img.resize((w, h))
    img.save(out_path)
    return out_path


def _fit_cover(clip, w, h):
    """Resize+crop a clip so it fully covers a w x h frame (no letterboxing)."""
    clip_ratio = clip.w / clip.h
    target_ratio = w / h
    if clip_ratio > target_ratio:
        clip = clip.resize(height=h)
    else:
        clip = clip.resize(width=w)
    return crop(clip, width=w, height=h, x_center=clip.w / 2, y_center=clip.h / 2)


VIDEO_EXTS = (".mp4", ".mov", ".m4v", ".webm", ".mkv")


def _local_clip_paths():
    return sorted(p for p in glob.glob(os.path.join(config.PARKOUR_DIR, "*"))
                  if p.lower().endswith(VIDEO_EXTS))


def _downloaded_clip_paths():
    """Real gameplay clips listed in PARKOUR_CLIP_URLS, downloaded once per
    run into work/parkour_cache/. For footage too big to commit to GitHub --
    host it anywhere with a direct link (e.g. your R2 bucket) instead."""
    if not config.PARKOUR_CLIP_URLS:
        return []
    os.makedirs(config.PARKOUR_CACHE_DIR, exist_ok=True)
    paths = []
    for url in config.PARKOUR_CLIP_URLS:
        parsed = urlparse(url)
        ext = os.path.splitext(parsed.path)[1].lower()
        name = hashlib.sha1(url.encode()).hexdigest()[:16] + (ext if ext in VIDEO_EXTS else ".mp4")
        path = os.path.join(config.PARKOUR_CACHE_DIR, name)
        if not os.path.exists(path):
            # Log host + filename only: a signed URL's query string is a credential.
            shown = f"{parsed.netloc}/{os.path.basename(parsed.path)}"
            try:
                with requests.get(url, stream=True, timeout=60) as resp:
                    resp.raise_for_status()
                    with open(path + ".part", "wb") as f:
                        for block in resp.iter_content(chunk_size=1 << 20):
                            f.write(block)
                os.replace(path + ".part", path)
                print(f"[assemble] downloaded parkour clip {shown}")
            except Exception as e:
                # Not str(e): requests puts the full (possibly signed) URL in it.
                status = getattr(getattr(e, "response", None), "status_code", None)
                print(f"[assemble] couldn't download parkour clip {shown}: "
                      f"{f'HTTP {status}' if status else type(e).__name__}")
                if os.path.exists(path + ".part"):
                    os.remove(path + ".part")
                continue
        paths.append(path)
    return paths


def build_parkour_background(total_duration, work_dir, w, h):
    """Reddit-story videos use ONE continuous parkour gameplay shot filling
    the vertical frame (the genre convention), not cut-together b-roll.

    Real footage wins when there is any: a random clip from assets/parkour/
    (or PARKOUR_CLIP_URLS) at a random start offset so repeat uploads don't
    all open on the same frame, looped if it's shorter than the video.
    Otherwise the gameplay is generated from scratch (src/gameplay.py) -- a
    brand-new block-parkour course every video, so there's always real
    moving gameplay behind the story, never a static background."""
    clip_paths = _local_clip_paths() or _downloaded_clip_paths()
    if clip_paths:
        path = random.choice(clip_paths)
        try:
            raw = VideoFileClip(path, audio=False)
            if raw.duration <= total_duration:
                bg = loop_video(raw, duration=total_duration)
            else:
                start = random.uniform(0, raw.duration - total_duration)
                bg = raw.subclip(start, start + total_duration)
            print(f"[assemble] background: gameplay clip {os.path.basename(path)}")
            return _fit_cover(bg, w, h), [raw]
        except Exception:
            print(f"[assemble] couldn't open {path} -- generating gameplay instead", file=sys.stderr)
            traceback.print_exc()

    try:
        print("[assemble] background: generated block-parkour gameplay "
              "(add real clips to assets/parkour/ or PARKOUR_CLIP_URLS to use those instead)")
        return gameplay.build_background(total_duration, w, h), []
    except Exception:
        # Should never happen, but a plain background beats losing the post.
        print("[assemble] gameplay generation FAILED -- using a plain gradient", file=sys.stderr)
        traceback.print_exc()
        img_path = os.path.join(work_dir, "fallback_bg.png")
        _gradient_fallback_image(img_path, w, h)
        return ImageClip(img_path).set_duration(total_duration), []


def assemble(narration_path, background_builder, caption_events, work_dir, out_path,
             w=None, h=None, story_title=None, category=None, title_end=None):
    """caption_events: [(start, end, chunk_words, active_index), ...] from
    captions.py. title_end: when the narrator finishes reading the title --
    the Reddit card is shown until then, and the captions take over after."""
    w = w or config.VIDEO_WIDTH
    h = h or config.VIDEO_HEIGHT
    os.makedirs(work_dir, exist_ok=True)

    narration = AudioFileClip(narration_path)
    total_duration = narration.duration

    background, raw_bg_clips = background_builder(total_duration, work_dir, w, h)
    background = background.set_duration(total_duration)

    caption_layers = []
    for idx, (start, end, words, active) in enumerate(caption_events):
        end = min(end, total_duration)
        if end <= start:
            continue
        png_path = os.path.join(work_dir, f"cap_{idx}.png")
        _, cap_h = _render_caption_png(words, active, png_path, w=w)
        layer = (
            ImageClip(png_path)
            .set_start(start)
            .set_duration(end - start)
            .set_position(("center", int(h * CAPTION_CENTER_Y - cap_h / 2)))
        )
        caption_layers.append(layer)

    brand_png = os.path.join(work_dir, "brand_bar.png")
    _render_brand_bar(brand_png, w=w)
    brand_layer = ImageClip(brand_png).set_duration(total_duration).set_position(("center", "top"))

    reddit_layer = None
    if story_title:
        reddit_png = os.path.join(work_dir, "reddit_card.png")
        _render_reddit_card_png(story_title, category, reddit_png, w=w)
        card_end = min(title_end or 4.0, total_duration)
        reddit_layer = (
            ImageClip(reddit_png)
            .set_duration(card_end)
            .set_position(("center", "center"))
            .crossfadeout(min(0.25, card_end / 2))
        )

    layers = [background, brand_layer]
    if reddit_layer is not None:
        layers.append(reddit_layer)
    layers += caption_layers

    video = CompositeVideoClip(layers, size=(w, h)).set_duration(total_duration)

    music_files = glob.glob(os.path.join(config.MUSIC_DIR, "*.mp3"))
    if music_files:
        music_path = random.choice(music_files)
        music = AudioFileClip(music_path)
        music = audio_loop(music, duration=total_duration)
        # The three bundled tracks are mastered hot (measured mean ~-11 to
        # -12.5 dB, peaking at 0 dB), so even a "quiet" linear multiplier
        # still reads as loud once bass/synth hits land under the narration.
        # 0.06 (~-24 dB) keeps it a felt-not-heard background bed instead of
        # competing with the voice. Tune this one number if it still needs
        # to move after a listen.
        music = volumex(music, 0.06)
        final_audio = CompositeAudioClip([music, narration])
    else:
        final_audio = narration

    video = video.set_audio(final_audio)
    video.write_videofile(
        out_path,
        fps=30,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        threads=4,
        temp_audiofile=os.path.join(work_dir, "temp-audio.m4a"),
        remove_temp=True,
        # moviepy's default proglog progress bar prints a fresh line per
        # frame/audio-chunk update instead of overwriting in place (since CI
        # logs aren't a real terminal) -- silence it entirely.
        logger=None,
    )

    narration.close()
    video.close()
    background.close()
    for raw in raw_bg_clips:
        raw.close()
    brand_layer.close()
    if reddit_layer is not None:
        reddit_layer.close()
    for layer in caption_layers:
        layer.close()
    if music_files:
        music.close()

    return out_path
