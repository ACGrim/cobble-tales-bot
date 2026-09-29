"""
Text-to-speech via edge-tts (Microsoft Edge's neural voices, free, no API key).

Using ONE consistent voice every day is what gives the channel a recognizable
"host" instead of feeling like a random TTS compilation.

Narration follows the genre format: the post title is read first (while the
mock Reddit card is on screen), a short beat, then the story itself. The two
are synthesized separately so we know exactly where the title ends, and
edge-tts's WordBoundary events give the start/end time of every spoken word
in the story -- that's what drives the word-by-word synced captions.
"""
import asyncio
import os
import re

import edge_tts
from moviepy.editor import AudioFileClip, CompositeAudioClip

from . import config

TITLE_GAP_SECONDS = 0.45  # beat between reading the title and starting the story

# Reddit shorthand the voice would otherwise read letter-by-letter or
# mangle. Applied to what's SPOKEN only -- the on-screen card keeps the
# original title text.
_SPOKEN_REPLACEMENTS = [
    (r"\bAITAH?\b", "Am I the A-hole"),
    (r"\bWIBTAH?\b", "Would I be the A-hole"),
    (r"\bTIFU\b", "Today I messed up"),
    (r"\bTL;?DR\b", "Too long, didn't read"),
    (r"\bMIL\b", "mother-in-law"),
    (r"\bFIL\b", "father-in-law"),
    (r"\bSIL\b", "sister-in-law"),
    (r"\bBIL\b", "brother-in-law"),
    (r"\bBF\b", "boyfriend"),
    (r"\bGF\b", "girlfriend"),
    (r"\bDH\b", "husband"),
    (r"\bOP\b", "O.P."),
    # "(27F)" / "(30M)" -> "27 female" / "30 male". Parenthesized only, so a
    # bare "$10M" is never read as "10 male".
    (r"\((\d{1,2}) ?[Ff]\)", r"\1 female"),
    (r"\((\d{1,2}) ?[Mm]\)", r"\1 male"),
]


def spoken_text(text):
    for pattern, repl in _SPOKEN_REPLACEMENTS:
        text = re.sub(pattern, repl, text)
    return text


async def _synthesize(text, out_path):
    """Writes the mp3 and returns [(start, end, word), ...] in seconds
    (empty if the installed edge-tts didn't report word boundaries)."""
    try:
        communicate = edge_tts.Communicate(
            text, config.TTS_VOICE, rate=config.TTS_RATE, boundary="WordBoundary"
        )
    except TypeError:  # edge-tts < 7 has no `boundary` arg (word boundaries were the default)
        communicate = edge_tts.Communicate(text, config.TTS_VOICE, rate=config.TTS_RATE)

    words = []
    with open(out_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 1e7  # edge-tts reports 100ns ticks
                words.append((start, start + chunk["duration"] / 1e7, chunk["text"]))
    return words


def synthesize(text, out_path):
    """Plain single-file narration. Returns word timings (may be empty)."""
    return asyncio.run(_synthesize(text, out_path))


def narrate(title, script, work_dir, out_path):
    """Narrates "<title> ... <story>" into one mp3 at out_path.

    Returns a dict:
      duration    total narration length (seconds)
      body_start  when the story starts (the title card should be gone by then)
      words       [(start, end, word), ...] for the story, on the combined
                  timeline -- empty if word timings weren't available
    """
    title_path = os.path.join(work_dir, "narration_title.mp3")
    body_path = os.path.join(work_dir, "narration_body.mp3")
    synthesize(spoken_text(title), title_path)
    body_words = synthesize(spoken_text(script), body_path)

    title_clip = AudioFileClip(title_path)
    body_clip = AudioFileClip(body_path)
    body_start = title_clip.duration + TITLE_GAP_SECONDS
    combined = CompositeAudioClip([title_clip, body_clip.set_start(body_start)])
    combined = combined.set_duration(body_start + body_clip.duration)
    combined.write_audiofile(out_path, fps=44100, logger=None)
    duration = combined.duration
    title_clip.close()
    body_clip.close()

    words = [(s + body_start, e + body_start, w) for s, e, w in body_words]
    return {"duration": duration, "body_start": body_start, "words": words}
