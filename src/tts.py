"""
Text-to-speech via edge-tts (Microsoft's neural voices, free, no API key).

Two consistent "hosts" -- one male, one female voice -- so a story whose
narrator is a woman ("my husband...") isn't read by a man, while the channel
still sounds the same day to day. See config.TTS_VOICE_MALE / _FEMALE.
"""
import asyncio
import os
import subprocess

import edge_tts

from . import config


def voice_for(narrator):
    """Picks the narration voice for a story's narrator ("male", "female" or
    "either"). config.TTS_VOICE, when set, overrides everything."""
    if config.TTS_VOICE:
        return config.TTS_VOICE
    if str(narrator).lower().startswith("f"):
        return config.TTS_VOICE_FEMALE
    return config.TTS_VOICE_MALE


async def _synthesize(text: str, out_path: str, voice: str):
    communicate = edge_tts.Communicate(text, voice, rate=config.TTS_RATE)
    await communicate.save(out_path)


def synthesize(text: str, out_path: str, voice: str = None, attempts: int = 4):
    """Retries: Microsoft's free TTS endpoint occasionally answers with no
    audio (edge_tts NoAudioReceived) for a request that works a moment later."""
    import time
    for i in range(attempts):
        try:
            asyncio.run(_synthesize(text, out_path, voice or voice_for("either")))
            return out_path
        except Exception as exc:
            if i == attempts - 1:
                raise
            print(f"[tts] attempt {i + 1} failed ({exc.__class__.__name__}); retrying")
            time.sleep(3 * (i + 1))


def synthesize_with_outro(text, out_path, voice, outro_text, gap=0.45):
    """Narrates the story, then (after a short pause) the follow call-to-action,
    in the same voice, into one file. Returns the time in seconds where the
    outro starts, so the video can show the follow card right then."""
    base, _ = os.path.splitext(out_path)
    story_path, outro_path = base + "_story.mp3", base + "_outro.mp3"
    synthesize(text, story_path, voice=voice)
    synthesize(outro_text, outro_path, voice=voice)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-i", story_path, "-f", "lavfi", "-t", str(gap), "-i", "anullsrc=r=24000:cl=mono", "-i", outro_path,
         "-filter_complex",
         "[0:a]aresample=24000,aformat=channel_layouts=mono[a0];"
         "[2:a]aresample=24000,aformat=channel_layouts=mono[a2];"
         "[a0][1:a][a2]concat=n=3:v=0:a=1[out]",
         "-map", "[out]", "-c:a", "libmp3lame", "-b:a", "96k", out_path],
        check=True,
    )
    return _duration(story_path) + gap


def _duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True, check=True).stdout.strip()
    return float(out)
