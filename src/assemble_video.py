"""
Assembles the final vertical (1080x1920) Reddit-story video from:
  - narration audio (mp3, from tts.py)
  - a continuous Minecraft parkour gameplay clip (from assets/parkour/),
    cover-cropped to fill the frame
  - burned-in captions (rendered with Pillow, NOT ImageMagick, so this runs
    cleanly on a stock GitHub Actions runner with no extra system config)
  - an optional looped background music bed from assets/music/
  - a small static brand wordmark bar

Deliberately avoids moviepy's TextClip (which shells out to ImageMagick and
needs a policy.xml patch to allow text rendering) in favor of Pillow-rendered
PNG overlays — one less fragile moving part in CI.
"""
import glob
import os
import random

from PIL import Image, ImageDraw, ImageFont

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

from . import config

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


def _render_caption_png(text, out_path, w=config.VIDEO_WIDTH, box_height=340, font_size=64):
    # moviepy's ImageClip decodes and holds the FULL image in memory for as
    # long as the clip object exists. Render onto a full-width canvas to
    # get correct text wrapping/centering, then crop down to just the
    # rounded-rect bubble (+ small margin) before saving, so each ImageClip
    # only ever holds as many pixels as the text needs.
    img = Image.new("RGBA", (w, box_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = _load_font(font_size)
    max_text_width = w - 120
    lines = _wrap_text(draw, text.upper(), font, max_text_width)

    line_heights = [draw.textbbox((0, 0), ln, font=font)[3] for ln in lines]
    total_h = sum(line_heights) + (len(lines) - 1) * 14
    pad_y, pad_x = 22, 34

    # Semi-transparent rounded background so captions stay legible over any footage.
    bg_top = (box_height - total_h) // 2 - pad_y
    bg_bottom = (box_height + total_h) // 2 + pad_y
    max_line_w = max(draw.textlength(ln, font=font) for ln in lines)
    bg_left = (w - max_line_w) / 2 - pad_x
    bg_right = (w + max_line_w) / 2 + pad_x
    draw.rounded_rectangle([bg_left, bg_top, bg_right, bg_bottom], radius=24, fill=(0, 0, 0, 160))

    y = (box_height - total_h) // 2
    for ln in lines:
        lw = draw.textlength(ln, font=font)
        draw.text(((w - lw) / 2, y), ln, font=font, fill=(255, 255, 255, 255))
        y += draw.textbbox((0, 0), ln, font=font)[3] + 14

    crop_margin = 6
    crop_box = (
        max(0, int(bg_left) - crop_margin),
        max(0, int(bg_top) - crop_margin),
        min(w, int(bg_right) + crop_margin),
        min(box_height, int(bg_bottom) + crop_margin),
    )
    img = img.crop(crop_box)

    img.save(out_path)
    return out_path


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


def build_parkour_background(total_duration, work_dir, w, h):
    """Reddit-story videos use ONE continuous Minecraft parkour gameplay
    clip cropped to fill the vertical frame, not several cut-together
    topical b-roll clips -- that's the genre convention, and it also means
    opening exactly one VideoFileClip (one ffmpeg reader) instead of many.
    Picks a random clip from assets/parkour/ and a random start offset so
    repeat uploads don't all open on the same frame; loops the clip if it's
    shorter than the video needs."""
    clip_paths = sorted(glob.glob(os.path.join(config.PARKOUR_DIR, "*.mp4")))
    if not clip_paths:
        print(f"[assemble] no parkour clips found in {config.PARKOUR_DIR} -- "
              f"using a plain gradient background instead. See "
              f"assets/parkour/README.txt.")
        img_path = os.path.join(work_dir, "fallback_bg.png")
        _gradient_fallback_image(img_path, w, h)
        return ImageClip(img_path).set_duration(total_duration), []

    path = random.choice(clip_paths)
    raw = VideoFileClip(path, audio=False)

    if raw.duration <= total_duration:
        bg = loop_video(raw, duration=total_duration)
    else:
        max_start = raw.duration - total_duration
        start = random.uniform(0, max_start)
        bg = raw.subclip(start, start + total_duration)

    bg = _fit_cover(bg, w, h)
    return bg, [raw]


def assemble(narration_path, background_builder, timed_captions, work_dir, out_path, w=None, h=None):
    w = w or config.VIDEO_WIDTH
    h = h or config.VIDEO_HEIGHT
    os.makedirs(work_dir, exist_ok=True)

    narration = AudioFileClip(narration_path)
    total_duration = narration.duration

    background, raw_bg_clips = background_builder(total_duration, work_dir, w, h)
    background = background.set_duration(total_duration)

    caption_layers = []
    for idx, (start, end, text) in enumerate(timed_captions):
        if end <= start:
            continue
        png_path = os.path.join(work_dir, f"cap_{idx}.png")
        _render_caption_png(text, png_path, w=w)
        layer = (
            ImageClip(png_path)
            .set_start(start)
            .set_duration(end - start)
            .set_position(("center", int(h * 0.66)))
        )
        caption_layers.append(layer)

    brand_png = os.path.join(work_dir, "brand_bar.png")
    _render_brand_bar(brand_png, w=w)
    brand_layer = ImageClip(brand_png).set_duration(total_duration).set_position(("center", "top"))

    video = CompositeVideoClip([background, brand_layer] + caption_layers, size=(w, h)).set_duration(total_duration)

    music_files = glob.glob(os.path.join(config.MUSIC_DIR, "*.mp3"))
    if music_files:
        music_path = random.choice(music_files)
        music = AudioFileClip(music_path)
        music = audio_loop(music, duration=total_duration)
        music = volumex(music, 0.14)
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
    for layer in caption_layers:
        layer.close()
    if music_files:
        music.close()

    return out_path
