Background clips of Pip, the Cobble Tales mascot, running a blocky obstacle
course. build_blocky_background() in src/assemble_video.py picks one at
random for each video, starts it at a random point, and scales it to fill
the 1080x1920 frame.

These are original animation rendered by tools/blocky_background/ -- no
third-party footage, so they're safe to monetize. The camera keeps Pip in
the band between the Reddit post card (top) and the captions (lower third).

Current clips (100 s each, 720x1280, 30 fps):
  blocky_sky_01.mp4    grassy sky islands over the sea
  blocky_candy_02.mp4  pastel cake platforms and lollipops
  blocky_lava_03.mp4   basalt blocks over a lava sea, drifting embers
  blocky_ice_04.mp4    snowy ice blocks and pine trees, light snowfall

Every clip includes coins, hurdles, spinning bars, bounce pads, moving
platforms, checkpoints, and one slip-and-respawn moment.

To add more variety, render new seeds (each seed is a different course):
    python tools/blocky_background/render_clips.py --themes sky,lava --seed 11
Keep each file well under GitHub's 100 MB limit.
