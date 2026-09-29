"""
Generates an ORIGINAL, Claude-written story in the voice and conventions of
viral "Reddit story" posts (AITA, TIFU, confession, revenge, etc.) for the
daily Instagram Reels + TikTok story videos.

This is deliberately NOT a scraper. Reddit's official API now requires
explicit pre-approval that's effectively closed to small/personal projects,
and the old unauthenticated ".json" endpoint trick was shut down in 2026 --
see SETUP_CROSSPOST.md. Writing wholly original stories sidesteps that
entirely, and is also the safer category under YouTube-style "reused
content" policies generally: nothing here is copied from a real person's
post, it's original narrative writing in a recognizable genre, the same way
a novel "written in the style of" something isn't a copy of it.

A title like "AITA for X" is used here as a genre convention/format label
(viewers immediately recognize the format), not a claim that this is a real
submitted post from a real person.
"""
import json
import re

import anthropic

from . import config

SYSTEM_PROMPT = """You write ORIGINAL fictional stories for a faceless Instagram Reels \
/ TikTok channel, in the authentic voice, pacing, and conventions of viral "Reddit \
story" narration videos (AITA, TIFU, confession, relationship, petty revenge, creepy \
encounter, and similar genres). Every story is entirely invented by you -- never a real \
person's real post, never based on a specific real submission -- but written to be \
indistinguishable in voice from a genuine one: first-person, casual internet vernacular, \
specific concrete details (not vague), a clear escalation, and a satisfying twist, \
reveal, or resolution near the end. A title like "AITA for X" is a recognized genre \
label, not a claim of real authorship.

Output ONLY valid JSON (no markdown fences, no commentary) matching this schema:
{
  "title": "string, <=100 chars, written like a genuine viral Reddit post title for \
this genre (e.g. 'AITA for telling my sister the truth the morning of her wedding?')",
  "hook": "string, the first line of the story (spoken right AFTER the title is read \
aloud), <=15 words, must earn the next 2 seconds -- raise the stakes or drop the viewer \
straight into the situation; never a restatement of the title",
  "script": "string, the FULL spoken story from first word to last (the title is read \
aloud separately just before it, so never repeat the title here), 140-220 words, \
written to be read aloud in 40-75 seconds at a natural, slightly breathless \
storytelling pace. First person, past tense, concrete specific details (names can be \
placeholders like 'my sister' rather than invented proper names). Build to a clear \
twist or resolution in the final 1-2 sentences. No stage directions, no bracketed \
notes.",
  "description": "string, 1-2 sentences for the post caption, written to make someone \
want to know how it ends -- includes a call to follow for daily stories",
  "tags": ["8-12 relevant hashtags for the genre, lowercase, no # symbol, e.g. \
'redditstories', 'storytime', 'aita'"]
}

Rules:
- The hook must be the literal first sentence of "script".
- The narrator reads the title aloud first, then "script" -- so "script" must not \
open by repeating or paraphrasing the title.
- This is fiction written in a genre's voice -- never claim or imply it happened to a \
real, identifiable person, and never use a real person's name.
- No profanity, no graphic violence, no sexual content, no hate speech -- keep it \
platform-safe for Reels/TikTok.
- Never invent fake statistics or claim the story is "100% true" -- let the story speak \
for itself the way genuine posts in this genre do, without over-promising authenticity.
- Stay strictly within the 140-220 word count for "script"; this drives the video's \
runtime directly.
"""


def generate(category: str) -> dict:
    config.require("ANTHROPIC_API_KEY")
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    message = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=1800,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Write today's story. Genre/prompt: {category}",
            }
        ],
    )

    raw = message.content[0].text.strip()
    raw = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()

    data = json.loads(raw)

    required = ["title", "hook", "script", "description", "tags"]
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(f"Claude output missing fields: {missing}\nRaw: {raw[:500]}")

    return data
