# Blocky course background

The background layer for Cobble Tales Reddit-story videos: **Pip**, the
channel's blocky mascot (orange hoodie, yellow cap), running an endless,
procedurally generated obstacle course. It replaces Minecraft parkour
footage with original animation the channel owns outright.

- `course.html`: the animated course (three.js, bundled in `vendor/`, MIT).
  Open it in a browser for a live preview:
  `course.html?theme=lava&seed=3`. Themes are `sky`, `candy`, `lava`
  and `ice`.
- `render_clips.py`: renders the course frame by frame in headless
  Chromium and encodes MP4 clips into `assets/blocky/`.

## What's in a course

Pillar hops, staircases, islands with coin rows, hurdles and spinning bars,
bounce pads, moving platforms, checkpoints (the flag turns green with
confetti), and about once a minute a missed jump: Pip falls, respawns at the
last checkpoint, and runs that part again. The same seed always makes the
same course, so clips can be re-rendered exactly.

## Framing

The camera follows from behind and keeps Pip between roughly 35% and 57%
of the frame height, which is the clear band between the Reddit post card
(top ~26%) and the burned-in captions (from 66% down). If the overlay layout
in `src/assemble_video.py` changes, adjust `CAM` in `course.html`.

## Rendering more clips

```
pip install playwright
python -m playwright install chromium
python tools/blocky_background/render_clips.py --themes sky,candy --seed 21 --seconds 100
```

Without a GPU this runs at about 2-4 frames per second per worker, so a
100-second clip takes 15-25 minutes. `--jobs` sets how many clips render at
the same time.
