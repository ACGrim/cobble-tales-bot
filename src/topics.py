"""
Picks the next topic/theme for today's video(s) and records it as used, so
the bot never repeats one until its bank has fully cycled through.

Generalized to work against either bank: the Shorts topic bank
(topics.json / used_topics.json) or the long-form deep-dive theme bank
(longform_themes.json / used_longform_themes.json). Pass bank_file/used_file
to target the long-form bank; omit them for the default Shorts bank.
"""
import json
from . import config


def get_next_topic(bank_file=None, used_file=None, extra_used=None):
    """Returns (topic, used_before) where used_before is the *persisted*
    used-set (not including extra_used) — pass it straight through to
    mark_topic_used() once the video for this topic succeeds.

    extra_used: topics already picked earlier in this same run (e.g. the
    other Shorts today) that should also be avoided, without being written
    to disk yet (in case this run fails before upload).
    """
    bank_file = bank_file or config.TOPICS_FILE
    used_file = used_file or config.USED_TOPICS_FILE
    extra_used = extra_used or set()

    with open(bank_file, "r", encoding="utf-8") as f:
        bank = json.load(f)
    all_items = bank["topics"]

    with open(used_file, "r", encoding="utf-8") as f:
        used_data = json.load(f)
    used = set(used_data.get("used", []))

    remaining = [t for t in all_items if t not in used and t not in extra_used]
    if not remaining:
        # Either the persisted bank fully cycled, or extra_used (this run's
        # earlier picks) ate everything that was left. Prefer avoiding
        # within-run repeats over avoiding across-run repeats.
        remaining = [t for t in all_items if t not in extra_used]
        if not remaining:
            remaining = all_items
        used = set()  # this pick starts a fresh persisted cycle

    topic = remaining[0]
    return topic, used


def mark_topic_used(topic, used_set, used_file=None):
    used_file = used_file or config.USED_TOPICS_FILE
    used_set = set(used_set)
    used_set.add(topic)
    with open(used_file, "w", encoding="utf-8") as f:
        json.dump({"used": sorted(used_set)}, f, indent=2)
