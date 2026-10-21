"""
Text-to-speech via edge-tts (Microsoft's neural voices, free, no API key).

Two consistent "hosts" -- one male, one female voice -- so a story whose
narrator is a woman ("my husband...") isn't read by a man, while the channel
still sounds the same day to day. See config.TTS_VOICE_MALE / _FEMALE.
"""
import asyncio

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


def synthesize(text: str, out_path: str, voice: str = None):
    asyncio.run(_synthesize(text, out_path, voice or voice_for("either")))
    return out_path
