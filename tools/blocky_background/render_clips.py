"""
Renders blocky-course background clips for the Reddit-story videos.

Drives course.html in headless Chromium frame by frame (fixed timestep, so the
output is smooth no matter how slow the machine is) and pipes the frames into
ffmpeg. Output goes to assets/blocky/ by default, where
assemble_video.build_blocky_background() picks them up.

    pip install playwright && python -m playwright install chromium
    python tools/blocky_background/render_clips.py                      # all four themes
    python tools/blocky_background/render_clips.py --themes lava --seed 21 --seconds 120

Each theme + seed makes a different course, so rendering more seeds is how
you grow the library. Rendering is CPU-bound without a GPU (roughly 2-4
frames/second per worker on a laptop-class CPU), so a 100 s clip at 30 fps
takes ~15-25 minutes. Keep clips well under GitHub's 100 MB file limit;
720x1280 at CRF 23 lands around 20-35 MB per 100 s.
"""
import argparse
import asyncio
import base64
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DEFAULT_OUT = os.path.join(ROOT, "assets", "blocky")
THEMES = ["sky", "candy", "lava", "ice"]
CHROME_ARGS = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]


async def render_one(pw, theme, seed, seconds, fps, w, h, crf, out_dir, batch=15):
    from_path = os.path.join(HERE, "course.html")
    out_path = os.path.join(out_dir, f"blocky_{theme}_{seed:02d}.mp4")
    tmp_path = out_path + ".part.mp4"
    total = int(round(seconds * fps))

    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-c:v", "mjpeg", "-framerate", str(fps), "-i", "-",
         "-c:v", "libx264", "-preset", "slow", "-crf", str(crf), "-pix_fmt", "yuv420p", "-movflags", "+faststart",
         "-an", tmp_path],
        stdin=subprocess.PIPE,
    )
    browser = await pw.chromium.launch(args=CHROME_ARGS)
    page = await browser.new_page(viewport={"width": w, "height": h})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    await page.goto("file://" + from_path + "?render=1")
    info = await page.evaluate(
        f"() => Course.setup({{theme: '{theme}', seed: {seed}, width: {w}, height: {h}, duration: {seconds}}})"
    )
    if info["duration"] < seconds:
        raise RuntimeError(f"{theme}: course only covers {info['duration']:.1f}s, need {seconds}s")

    start = time.time()
    done = 0
    while done < total:
        n = min(batch, total - done)
        urls = await page.evaluate(f"() => Course.frames({done / fps}, {n}, {fps}, 0.93)")
        for u in urls:
            ff.stdin.write(base64.b64decode(u.split(",", 1)[1]))
        done += n
        if done % (batch * 20) == 0 or done == total:
            el = time.time() - start
            print(f"[{theme}] {done}/{total} frames  {done / el:.1f} fps  ~{(total - done) / max(done / el, 0.01) / 60:.1f} min left", flush=True)
        if errors:
            raise RuntimeError(f"{theme}: page error: {errors[0]}")
    await browser.close()
    ff.stdin.close()
    if ff.wait() != 0:
        raise RuntimeError(f"{theme}: ffmpeg failed")
    os.replace(tmp_path, out_path)
    print(f"[{theme}] wrote {out_path} ({os.path.getsize(out_path) / 1e6:.1f} MB)", flush=True)
    return out_path


async def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--themes", default=",".join(THEMES))
    ap.add_argument("--seed", type=int, default=1, help="course seed; each theme gets seed + its index")
    ap.add_argument("--seconds", type=float, default=100)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--width", type=int, default=720)
    ap.add_argument("--height", type=int, default=1280)
    ap.add_argument("--crf", type=int, default=23)
    ap.add_argument("--jobs", type=int, default=2, help="clips rendered at the same time")
    ap.add_argument("--out", default=DEFAULT_OUT)
    a = ap.parse_args()

    from playwright.async_api import async_playwright

    os.makedirs(a.out, exist_ok=True)
    themes = [t.strip() for t in a.themes.split(",") if t.strip()]
    sem = asyncio.Semaphore(a.jobs)
    async with async_playwright() as pw:
        async def guarded(i, t):
            async with sem:
                return await render_one(pw, t, a.seed + i, a.seconds, a.fps, a.width, a.height, a.crf, a.out)
        results = await asyncio.gather(*(guarded(i, t) for i, t in enumerate(themes)), return_exceptions=True)
    failed = [r for r in results if isinstance(r, Exception)]
    for r in failed:
        print("FAILED:", r, file=sys.stderr)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
