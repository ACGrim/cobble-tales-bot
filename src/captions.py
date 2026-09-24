"""
Turns the caption chunk list into timed (start, end, text) triples.

We don't have word-level forced alignment (that would need an extra heavy
dependency), so we time each chunk proportionally to its character count
against the actual TTS audio duration. This is not frame-perfect but is
consistently close enough for short punchy captions.
"""


def time_captions(caption_chunks, audio_duration_seconds):
    total_chars = sum(len(c) for c in caption_chunks) or 1
    timed = []
    t = 0.0
    for chunk in caption_chunks:
        share = len(chunk) / total_chars
        dur = max(audio_duration_seconds * share, 0.4)
        timed.append((t, t + dur, chunk))
        t += dur

    # Stretch/shrink the last entry so timings exactly fill the audio.
    if timed:
        start, _, text = timed[-1]
        timed[-1] = (start, audio_duration_seconds, text)

    return timed


import re as _re


def chunk_script(text, min_words=3, max_words=7):
    """Splits a long narration string into short caption chunks (3-8ish words
    each) that together reconstitute the text verbatim (just re-chunked),
    without needing the model to hand us a duplicate, pre-chunked array.

    Used for the long-form video, where asking Claude to also emit a chunked
    captions array would roughly double its output size for ~1500+ words of
    script. Splits on whitespace, keeping punctuation attached to its word,
    and tries to break at sentence-ish boundaries (. ! ? ,) when a chunk is
    already at least min_words long, otherwise just caps at max_words.
    """
    words = text.split()
    chunks = []
    current = []
    for w in words:
        current.append(w)
        ends_clause = bool(_re.search(r"[.!?,:]$", w))
        if len(current) >= max_words or (ends_clause and len(current) >= min_words):
            chunks.append(" ".join(current))
            current = []
    if current:
        chunks.append(" ".join(current))
    return chunks
