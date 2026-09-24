"""
Text-to-speech via edge-tts (Microsoft Edge's neural voices, free, no API key).

Using ONE consistent voice every day is what gives the channel a recognizable
"host" instead of feeling like a random TTS compilation.
"""
import asyncio

import edge_tts

from . import config


async def _synthesize(text: str, out_path: str):
    communicate = edge_tts.Communicate(text, config.TTS_VOICE, rate="+2%")
    await communicate.save(out_path)


def synthesize(text: str, out_path: str):
    asyncio.run(_synthesize(text, out_path))
    return out_path
