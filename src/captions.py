"""
Caption timing.

Normally captions are word-synced: edge-tts reports exactly when each word is
spoken (see tts.py), and word_caption_events() turns that into short 1-3 word
on-screen chunks with the current word highlighted.

If word timings are ever unavailable, proportional_caption_events() falls
back to timing each chunk by its share of the characters against the actual
narration length -- not frame-perfect, but close enough for short chunks.
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


# --- Word-synced captions -------------------------------------------------
# Caption "events" are (start, end, chunk_words, active_index): one short
# chunk of 1-3 words on screen, with chunk_words[active_index] highlighted
# as it's spoken (active_index None = no highlight, used by the fallback).


def word_caption_events(words, max_words=3, max_chars=15, pause=0.22, linger=0.45):
    """Groups edge-tts word timings [(start, end, word), ...] into short
    on-screen chunks -- breaking on a natural pause (sentence/comma breaks in
    the voice) or when a chunk gets too long -- and emits one event per word
    so the highlight moves along with the narration."""
    chunks, cur = [], []
    for start, end, word in words:
        if cur:
            gap = start - cur[-1][1]
            chars = sum(len(w) + 1 for _, _, w in cur) + len(word)
            if len(cur) >= max_words or chars > max_chars or gap > pause:
                chunks.append(cur)
                cur = []
        cur.append((start, end, word))
    if cur:
        chunks.append(cur)

    events = []
    for ci, chunk in enumerate(chunks):
        chunk_end = chunk[-1][1] + linger
        if ci + 1 < len(chunks):
            chunk_end = min(chunk_end, chunks[ci + 1][0][0])
        texts = [w for _, _, w in chunk]
        for k, (start, _, _) in enumerate(chunk):
            end = chunk[k + 1][0] if k + 1 < len(chunk) else chunk_end
            events.append((start, end, texts, k))  # zero-length ones are skipped when assembling
    return events


def proportional_caption_events(script, start, end):
    """Fallback when word timings aren't available: short chunks of the
    script timed by character count across [start, end]."""
    chunks = chunk_script(script, min_words=2, max_words=4)
    return [(start + s, start + e, text.split(), None)
            for s, e, text in time_captions(chunks, max(end - start, 0.1))]
