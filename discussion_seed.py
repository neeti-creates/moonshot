#!/usr/bin/env python3
"""Free, zero-cost daily discussion poster for MoonshotHunt.

Picks the next curated prompt (cycling) and posts it as a new active
topic via store.add_topic(active=True). No network/API calls, no external cost.

Run via cron (e.g. daily). Env: DATA_DIR (default "data").
"""
import os
import json

import store

# Curated, honest discussion prompts (authored, not fabricated data).
PROMPTS = [
    ("What's the hardest part of piloting climate hardware in India?",
     "From lab validation to a deployed pilot, founders hit procurement, "
     "grid approvals, and long sales cycles. What surprised you most, and "
     "what would you tell a first-time climate-hardware founder?"),
    ("Where is 'deep tech' over-hyped right now?",
     "Not everything labelled deep tech is deep. Which sub-sectors are riding "
     "the label without the substance — and which quietly are?"),
    ("Is pre-seed climate capital actually flowing, or just announced?",
     "We see a lot of climate funds announced. Founders: are term sheets "
     "actually landing at the pre-seed stage? What's the real signal vs noise?"),
    ("Carbon removal: real market or future promise?",
     "Permanent removal vs avoidance credits — where should a founder bet, "
     "and what would make you trust a removal claim?"),
    ("AI for science: hype or inflection?",
     "Foundation models are hitting the lab. Where is AI genuinely accelerating "
     "discovery versus just producing plausible slides?"),
    ("Robotics in the real world: what actually shipped?",
     "Autonomous systems look great in demos. What's genuinely deployed today, "
     "and what bottleneck (data, actuators, regulation) is still holding it back?"),
    ("The talent question: can climate/deep-tech hire fast enough?",
     "Founders and VCs both say hiring is the constraint. What roles are "
     "impossible to fill, and how are you solving it?"),
    ("Should founders obsess over verification badges?",
     "We label claims 'self-reported, not due diligence.' Do buyers/VCs actually "
     "care, or is traction all that matters at pre-seed?"),
    ("What would make you back a first-time deep-tech founder?",
     "VCs: beyond the tech, what's the non-negotiable signal that makes you "
     "write the first cheque?"),
    ("Water, agriculture, resilience: the quiet climate markets?",
     "Energy and carbon get the spotlight. Which under-the-radar climate "
     "sub-sectors are you most bullish on, and why?"),
]


def _state_path():
    return os.path.join(store.DATA_DIR or "data", "seed_idx.json")


def next_prompt():
    p = _state_path()
    idx = 0
    if os.path.exists(p):
        try:
            idx = json.load(open(p)).get("idx", 0) % len(PROMPTS)
        except Exception:
            idx = 0
    title, body = PROMPTS[idx]
    nxt = (idx + 1) % len(PROMPTS)
    json.dump({"idx": nxt}, open(p, "w"))
    return title, body


def main():
    data_dir = os.environ.get("DATA_DIR", "data")
    store.init(data_dir)
    title, body = next_prompt()
    # Author the daily prompt as the platform (no fabricated person);
    # it becomes the new active topic (older topics stay in the list).
    store.add_topic(title, body, "hello@moonshot.hunt", "MoonshotHunt", active=True)
    print("Posted daily topic:", title)


if __name__ == "__main__":
    main()
