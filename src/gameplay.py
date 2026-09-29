"""
Procedurally rendered, first-person, Minecraft-*style* block parkour
gameplay -- the background layer for Reddit-story videos whenever there's no
real recorded footage available (assets/parkour/ empty and no
PARKOUR_CLIP_URLS set).

Why render it instead of shipping a clip: real gameplay recordings are big
(GitHub rejects files over 100MB), and footage recorded by someone else is a
copyright problem (see assets/parkour/README.txt). Everything here is drawn
from scratch at runtime -- procedurally generated 16x16 block textures,
a randomly generated floating parkour course, and a tiny textured voxel
renderer written in numpy. No Mojang/Minecraft assets are used anywhere; it's
an original look-alike in the genre's visual style, and every video gets a
brand-new course.

How the renderer works (per frame):
  1. Build one camera ray per pixel for the current camera pose.
  2. Paint the sky gradient, then intersect rays with a cloud plane above and
     a water plane far below (cheap: one plane intersection each).
  3. For every block face near the camera that faces it, project its four
     corners to get a screen-space bounding box, intersect only those
     pixels' rays with the face's plane, depth-test against a z-buffer, and
     sample the block's texture. Distance fog blends everything into the
     horizon color, like the real game.
  4. Draw a simple blocky first-person arm, then nearest-neighbor upscale
     to the output size (the chunky pixels are part of the look, and
     rendering at half resolution keeps it fast enough for CI).

Run standalone to preview:  python -m src.gameplay preview.mp4 --seconds 12
"""
import bisect
import math
import random

import numpy as np
from PIL import Image, ImageDraw

TEX = 16  # block texture resolution, like the real game's default pack

# Face order used everywhere below: +x, -x, +y (top), -y (bottom), +z, -z.
# Fixed per-face shading instead of real lighting is exactly how the game
# itself shades blocks, and it's what makes the cubes read as 3D.
FACE_SHADE = np.array([0.62, 0.62, 1.0, 0.5, 0.8, 0.8], np.float32)
FACE_AXIS = [0, 0, 1, 1, 2, 2]
FACE_SIGN = [1, -1, 1, -1, 1, -1]
FACE_NORMALS = [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)]

SKY_ZENITH = np.array([118, 166, 255], np.float32)
SKY_HORIZON = np.array([196, 219, 255], np.float32)
FOG_COLOR = SKY_HORIZON
CLOUD_COLOR = np.array([250, 251, 255], np.float32)
WATER_COLOR = np.array([52, 98, 214], np.float32)
FOG_START = 26.0
FOG_END = 92.0
NEAR = 0.05

EYE_HEIGHT = 1.62
RUN_SPEED = 5.2      # blocks/sec on the ground (the game's sprint is ~5.6)
WATER_DEPTH = 22.0   # how far below the start platform the sea sits
CLOUD_HEIGHT = 62.0  # how far above the start platform the cloud layer sits
VERTICAL_FOV_DEG = 78.0


# --- Procedural block textures ---------------------------------------------

def _noise_tex(rng, base, var):
    base = np.array(base, np.float32)
    shade = 1.0 + rng.uniform(-var, var, (TEX, TEX, 1)).astype(np.float32)
    return base * shade


def _speckle(rng, tex, count, factor):
    for _ in range(count):
        y, x = rng.integers(0, TEX, 2)
        tex[y, x] *= factor
    return tex


def _grass_top(rng):
    return _speckle(rng, _noise_tex(rng, (104, 168, 62), 0.16), 18, 0.82)


def _dirt(rng):
    return _speckle(rng, _noise_tex(rng, (134, 96, 67), 0.18), 20, 0.75)


def _grass_side(rng):
    tex = _dirt(rng)
    green = _noise_tex(rng, (96, 158, 58), 0.14)
    for x in range(TEX):
        depth = 3 + int(rng.random() < 0.45) + int(rng.random() < 0.15)
        tex[:depth, x] = green[:depth, x]
    return tex


def _stone(rng):
    tex = _noise_tex(rng, (127, 127, 127), 0.09)
    for _ in range(7):  # short darker streaks
        y, x = rng.integers(0, TEX, 2)
        tex[y, x:x + rng.integers(2, 5)] *= 0.82
    return tex


def _cobblestone(rng):
    # Voronoi cells = individual stones, darker where two cells meet = mortar.
    seeds = rng.uniform(0, TEX, (11, 2))
    shades = rng.uniform(95, 150, 11)
    yy, xx = np.mgrid[0:TEX, 0:TEX] + 0.5
    d = []
    for sy, sx in seeds:
        dy = np.minimum(abs(yy - sy), TEX - abs(yy - sy))  # tiles seamlessly
        dx = np.minimum(abs(xx - sx), TEX - abs(xx - sx))
        d.append(np.hypot(dy, dx))
    d = np.stack(d)
    order = np.argsort(d, axis=0)
    nearest, second = order[0], order[1]
    gap = np.take_along_axis(d, order[1:2], 0)[0] - np.take_along_axis(d, order[0:1], 0)[0]
    val = shades[nearest] * (1 + rng.uniform(-0.06, 0.06, (TEX, TEX)))
    val = np.where(gap < 1.1, val * 0.55, val)
    del second
    return np.repeat(val[..., None], 3, axis=2).astype(np.float32)


def _planks(rng):
    base = np.array((170, 136, 86), np.float32)
    tex = np.zeros((TEX, TEX, 3), np.float32)
    for p in range(4):
        rows = slice(p * 4, p * 4 + 4)
        shade = rng.uniform(0.92, 1.05)
        tex[rows] = base * shade * (1 + rng.uniform(-0.05, 0.05, (4, TEX, 1)))
        tex[p * 4 + 3] *= 0.68  # seam between planks
        seam = int(rng.integers(0, TEX))
        tex[rows, seam] *= 0.72
        for _ in range(3):  # wood grain
            gy = p * 4 + int(rng.integers(0, 3))
            gx = int(rng.integers(0, TEX - 4))
            tex[gy, gx:gx + int(rng.integers(2, 6))] *= 0.88
    return tex


def _sand(rng):
    return _speckle(rng, _noise_tex(rng, (220, 208, 162), 0.05), 14, 0.9)


def _bricks(rng):
    tex = _noise_tex(rng, (152, 78, 60), 0.1)
    mortar = np.array((176, 168, 160), np.float32)
    for row in range(0, TEX, 4):
        tex[row + 3] = mortar
        offset = 0 if (row // 4) % 2 == 0 else 4
        for x in (offset, offset + 8):
            tex[row:row + 3, x % TEX] = mortar
    return tex


def _wool(rng, color):
    tex = _noise_tex(rng, color, 0.07)
    yy, xx = np.mgrid[0:TEX, 0:TEX]
    tex *= (1 + 0.05 * ((xx + yy) % 2))[..., None]
    return tex


def _bevel(rng, color):
    tex = _noise_tex(rng, color, 0.05)
    tex[0, :] *= 1.18
    tex[:, 0] *= 1.18
    tex[-1, :] *= 0.72
    tex[:, -1] *= 0.72
    for _ in range(4):  # little highlights, like a polished ore block
        y, x = rng.integers(2, TEX - 3, 2)
        tex[y, x:x + 2] *= 1.2
    return tex


def _quartz(rng):
    tex = _noise_tex(rng, (236, 231, 224), 0.025)
    tex[0, :] *= 0.9
    tex[-1, :] *= 0.9
    return tex


WOOL_COLORS = [
    (206, 52, 48),    # red
    (235, 128, 32),   # orange
    (246, 208, 58),   # yellow
    (112, 186, 40),   # lime
    (60, 176, 218),   # light blue
    (52, 72, 170),    # blue
    (170, 64, 186),   # magenta
]


def _build_texture_atlas(rng):
    """Returns (atlas, names): atlas is float32 [n_types, 6 faces, 16, 16, 3]
    with the per-face shading already baked in."""
    dirt = _dirt(rng)
    grass = (_grass_side(rng), _grass_top(rng), dirt)
    defs = {"grass": grass}
    for name, fn in [("stone", _stone), ("cobble", _cobblestone), ("planks", _planks),
                     ("sand", _sand), ("bricks", _bricks), ("quartz", _quartz)]:
        t = fn(rng)
        defs[name] = (t, t, t)
    defs["dirt"] = (dirt, dirt, dirt)
    for i, c in enumerate(WOOL_COLORS):
        t = _wool(rng, c)
        defs[f"wool{i}"] = (t, t, t)
    for name, c in [("gold", (248, 206, 52)), ("emerald", (46, 196, 96)),
                    ("diamond", (98, 219, 214))]:
        t = _bevel(rng, c)
        defs[name] = (t, t, t)

    names = list(defs)
    atlas = np.zeros((len(names), 6, TEX, TEX, 3), np.float32)
    for i, name in enumerate(names):
        side, top, bottom = defs[name]
        for f in range(6):
            src = top if f == 2 else bottom if f == 3 else side
            atlas[i, f] = np.clip(src, 0, 255) * FACE_SHADE[f]
    return atlas, names


# --- Course generation ------------------------------------------------------

# Each theme is a run of jumps built from one palette; a checkpoint platform
# marks every theme change, like a real parkour map's stages.
THEMES = [
    ["grass"],
    ["stone", "cobble"],
    ["cobble"],
    ["planks"],
    ["sand"],
    ["bricks"],
    ["quartz"],
    ["rainbow"],
]
CHECKPOINTS = ["gold", "emerald", "diamond"]
PILLAR_UNDER = {"grass": "dirt", "sand": "sand", "planks": "planks",
                "stone": "stone", "cobble": "cobble", "bricks": "bricks",
                "quartz": "quartz"}


class _Course:
    def __init__(self, rng, names, min_seconds):
        self.rng = rng
        self.type_id = {n: i for i, n in enumerate(names)}
        self.blocks = {}        # (x, y, z) -> type id
        self.owner = {}         # (x, z) column -> list of (y, node index)
        self.nodes = []         # [(x, y, z, radius)] blocks the player lands on
        self._generate(min_seconds)

    def _put(self, pos, name, node_idx):
        self.blocks[pos] = self.type_id[name]
        self.owner.setdefault((pos[0], pos[2]), []).append((pos[1], node_idx))

    def _clear(self, x, y, z, recent_from):
        # Keep a buffer of air around each new block (and headroom above it)
        # so the course never crosses back through itself.
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                for by, idx in self.owner.get((x + dx, z + dz), ()):
                    if idx < recent_from and y - 3 <= by <= y + 3:
                        return False
        return True

    def _platform(self, cx, y, cz, name, idx):
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                self._put((cx + dx, y, cz + dz), name, idx)

    def _generate(self, min_seconds):
        rng = self.rng
        heading = rng.uniform(0, 2 * math.pi)
        x, y, z = 0, 0, 0
        self._platform(x, y, z, "cobble", 0)
        self.nodes.append((x, y, z, 1.3))

        theme = list(THEMES[rng.integers(len(THEMES))])
        stage_len = int(rng.integers(10, 17))
        stage_i = 0
        rainbow_i = int(rng.integers(len(WOOL_COLORS)))
        next_turn = int(rng.integers(8, 16))
        est_seconds = 0.0

        while est_seconds < min_seconds:
            idx = len(self.nodes)
            prev_radius = self.nodes[-1][3]
            checkpoint = stage_i >= stage_len

            next_turn -= 1
            if next_turn <= 0:
                heading += rng.choice([-1, 1]) * rng.uniform(0.5, 1.1)
                next_turn = int(rng.integers(8, 16))

            placed = False
            for attempt in range(40):
                if checkpoint or prev_radius > 1:
                    dist, dy = int(rng.integers(3, 5)), int(rng.choice([-1, 0, 0]))
                elif rng.random() < 0.12:
                    dist, dy = 1, 0
                else:
                    dist = int(rng.choice([2, 3, 3, 4]))
                    dy = int(rng.choice([-1, 0, 0, 0, 1])) if dist <= 3 else int(rng.choice([-1, 0, 0]))
                if y >= 9:
                    dy = min(dy, 0)
                if y <= -6:
                    dy = max(dy, 0)
                h = heading + rng.normal(0, 0.28) + (attempt // 10) * rng.uniform(-1.2, 1.2)
                nx = x + int(round(math.cos(h) * dist))
                nz = z + int(round(math.sin(h) * dist))
                ny = y + dy
                d = math.hypot(nx - x, nz - z)
                if d < 1 or d > 4.6 or (dist > 1 and d < 1.9):
                    continue
                if checkpoint and d < 2.9:
                    continue
                if not self._clear(nx, ny, nz, recent_from=idx - 2):
                    continue
                placed = True
                break
            if not placed:
                heading += math.pi / 2
                continue

            if checkpoint:
                self._platform(nx, ny, nz, CHECKPOINTS[int(rng.integers(len(CHECKPOINTS)))], idx)
                self.nodes.append((nx, ny, nz, 1.3))
                theme = list(THEMES[rng.integers(len(THEMES))])
                stage_len = int(rng.integers(10, 17))
                stage_i = 0
            else:
                if theme == ["rainbow"]:
                    name = f"wool{rainbow_i % len(WOOL_COLORS)}"
                    rainbow_i += 1
                else:
                    name = theme[int(rng.integers(len(theme)))]
                self._put((nx, ny, nz), name, idx)
                # Some blocks sit on short pillars, like towers in a real map.
                if name in PILLAR_UNDER and rng.random() < 0.22:
                    for k in range(1, int(rng.integers(2, 5))):
                        self._put((nx, ny - k, nz), PILLAR_UNDER[name], idx)
                self.nodes.append((nx, ny, nz, 0.32))
                stage_i += 1

            est_seconds += 0.12 + (0.36 + 0.07 * d if d > 1.6 else d / RUN_SPEED)
            x, y, z = nx, ny, nz

    def arrays(self):
        pos = np.array(list(self.blocks.keys()), np.int32)
        types = np.array(list(self.blocks.values()), np.int32)
        faces = np.zeros((len(pos), 6), bool)
        for i, (bx, by, bz) in enumerate(pos):
            for f, (nx, ny, nz) in enumerate(FACE_NORMALS):
                faces[i, f] = (bx + nx, by + ny, bz + nz) not in self.blocks
        return pos, types, faces


class _Motion:
    """The player's path through the course as a list of timed segments:
    short sprints across each block's top, and parabolic jumps between them."""

    def __init__(self, nodes):
        self.t0, self.segs = [], []
        t = 0.0
        tops = [np.array([x + 0.5, y + 1.0, z + 0.5]) for x, y, z, _ in nodes]
        cur = tops[0].copy()
        for i in range(len(nodes) - 1):
            a, b = tops[i], tops[i + 1]
            ra, rb = nodes[i][3], nodes[i + 1][3]
            flat = b - a
            flat[1] = 0
            dh = float(np.linalg.norm(flat))
            direction = flat / max(dh, 1e-6)
            if dh < 1.6 and b[1] == a[1]:
                t = self._add(t, cur, b, None)
                cur = b.copy()
                continue
            takeoff = a + direction * ra
            landing = b - direction * rb
            landing[1] = b[1]
            t = self._add(t, cur, takeoff, None)
            jump_len = float(np.linalg.norm((landing - takeoff)[[0, 2]]))
            t = self._add(t, takeoff, landing, self._arc(b[1] - a[1]),
                          duration=0.36 + 0.07 * jump_len)
            cur = landing
        self.end = t
        self.landings = [s[0] + s[1] for s in self.segs if s[4] is not None]

    @staticmethod
    def _arc(dy, peak=1.25):
        # Parabola y(s) = a*s^2 + b*s through (0, 0) and (1, dy) whose apex
        # is `peak` above the takeoff height -- a plausible jump for any dy.
        b = 2 * peak + 2 * math.sqrt(max(peak * peak - peak * dy, 0.0))
        return (dy - b, b)

    def _add(self, t, p0, p1, arc, duration=None):
        if duration is None:
            duration = max(float(np.linalg.norm((p1 - p0)[[0, 2]])) / RUN_SPEED, 0.04)
        self.t0.append(t)
        self.segs.append((t, duration, p0.copy(), p1.copy(), arc))
        return t + duration

    def position(self, t):
        t = min(max(t, 0.0), self.end - 1e-6)
        i = max(bisect.bisect_right(self.t0, t) - 1, 0)
        start, dur, p0, p1, arc = self.segs[i]
        s = min(max((t - start) / dur, 0.0), 1.0)
        p = p0 + (p1 - p0) * s
        if arc is not None:
            a, b = arc
            p[1] = p0[1] + a * s * s + b * s
        return p

    def since_landing(self, t):
        i = bisect.bisect_right(self.landings, t) - 1
        return t - self.landings[i] if i >= 0 else 99.0


# --- Renderer ---------------------------------------------------------------

class ParkourGameplay:
    """Callable as a moviepy make_frame: frame(t) -> HxWx3 uint8 array.
    Pure function of t (moviepy may request frames out of order)."""

    def __init__(self, duration, width, height, seed=None, render_scale=2):
        self.rng = np.random.default_rng(seed if seed is not None else random.randrange(1 << 30))
        self.out_w, self.out_h = width, height
        self.w, self.h = max(width // render_scale, 16), max(height // render_scale, 16)
        self.duration = duration

        self.atlas, names = _build_texture_atlas(self.rng)
        # The course generator only estimates run time; build until the real
        # timeline (plus the camera's look-ahead) covers the whole video.
        min_seconds = duration + 4.0
        while True:
            course = _Course(self.rng, names, min_seconds=min_seconds)
            self.motion = _Motion(course.nodes)
            if self.motion.end >= duration + 2.0:
                break
            min_seconds += 8.0
        self.pos, self.types, self.faces = course.arrays()
        self.centers = self.pos.astype(np.float32) + 0.5

        self.f = (self.h / 2) / math.tan(math.radians(VERTICAL_FOV_DEG) / 2)
        jj, ii = np.meshgrid(np.arange(self.w, dtype=np.float32), np.arange(self.h, dtype=np.float32))
        self.xs = (jj + 0.5 - self.w / 2) / self.f
        self.ys = -(ii + 0.5 - self.h / 2) / self.f
        self.ys_row = self.ys[:, 0].copy()

        start = course.nodes[0]
        self.water_y = start[1] + 1 - WATER_DEPTH
        self.cloud_y = start[1] + 1 + CLOUD_HEIGHT
        self.cloud_cells = self.rng.random((64, 64)) < 0.27
        self.sway_phase = self.rng.uniform(0, 2 * math.pi, 3)

    # Camera --------------------------------------------------------------

    def _camera(self, t):
        m = self.motion
        p = m.position(t)
        # Look toward where the player is about to be, averaged over the next
        # ~1.5s, so the view turns smoothly into corners like a real player.
        ahead = np.mean([m.position(t + dt) for dt in (0.3, 0.6, 0.9, 1.2)], axis=0)
        v = ahead - p
        yaw = math.atan2(v[2], v[0]) if abs(v[0]) + abs(v[2]) > 1e-3 else 0.0
        ph = self.sway_phase
        yaw += 0.035 * math.sin(0.9 * t + ph[0]) + 0.015 * math.sin(2.3 * t + ph[1])
        slope = math.atan2(v[1], max(math.hypot(v[0], v[2]), 1e-3))
        pitch = math.radians(-24 + 3 * math.sin(0.23 * t + ph[2])) + 0.3 * slope

        eye = p + np.array([0.0, EYE_HEIGHT, 0.0])
        dt_land = m.since_landing(t)
        if dt_land < 0.16:  # small camera dip on each landing
            eye[1] -= 0.09 * math.sin(math.pi * dt_land / 0.16)
        return eye, yaw, pitch

    # Frame ---------------------------------------------------------------

    def __call__(self, t):
        eye, yaw, pitch = self._camera(t)
        cp, sp, cy, sy = math.cos(pitch), math.sin(pitch), math.cos(yaw), math.sin(yaw)
        fwd = np.array([cp * cy, sp, cp * sy], np.float32)
        right = np.array([-sy, 0.0, cy], np.float32)
        up = np.cross(right, fwd)

        # Ray direction per pixel, scaled so that depth along `fwd` is exactly
        # the ray parameter t. The camera never rolls (right has no y
        # component), so the vertical part depends only on the row: the
        # horizon is a straight line and sky/water can be drawn as row slices.
        H, W = self.h, self.w
        xs, ys = self.xs, self.ys
        dy_row = (fwd[1] + self.ys_row * up[1]).astype(np.float32)
        D = [fwd[0] + xs * right[0] + ys * up[0],
             np.broadcast_to(dy_row[:, None], (H, W)),
             fwd[2] + xs * right[2] + ys * up[2]]
        horizon = int(np.searchsorted(-dy_row, 0.0))  # first row looking down

        img = np.empty((H, W, 3), np.float32)
        depth = np.full((H, W), np.inf, np.float32)
        if horizon > 0:
            elev = dy_row[:horizon] / np.sqrt(dy_row[:horizon] ** 2 + 1.0)
            k = np.clip(elev * 2.4 + 0.05, 0, 1)[:, None]
            img[:horizon] = (SKY_HORIZON * (1 - k) + SKY_ZENITH * k)[:, None, :]
            self._draw_clouds(img[:horizon], D[0][:horizon], dy_row[:horizon], D[2][:horizon], eye, t)
        if horizon < H:
            self._draw_water(img[horizon:], D[0][horizon:], dy_row[horizon:], D[2][horizon:], eye, t)
        self._draw_blocks(img, depth, D, eye, fwd, right, up)

        frame = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
        self._draw_arm(frame, t)
        if frame.size != (self.out_w, self.out_h):
            frame = frame.resize((self.out_w, self.out_h), Image.NEAREST)
        return np.asarray(frame)

    def _draw_clouds(self, img, dx, dy_row, dz, eye, t):
        rows = dy_row > 1e-3
        if not rows.any():
            return
        first = int(np.argmax(rows))
        img, dx, dz, dy_row = img[first:], dx[first:], dz[first:], dy_row[first:]
        tt = ((self.cloud_y - eye[1]) / dy_row)[:, None]
        hx = eye[0] + tt * dx + t * 1.2  # clouds drift slowly
        hz = eye[2] + tt * dz
        cells = self.cloud_cells[np.floor(hz * (1 / 12)).astype(np.int32) & 63,
                                 np.floor(hx * (1 / 12)).astype(np.int32) & 63]
        fade = np.clip(1 - (tt - 70) / 300, 0, 1) * 0.9
        alpha = (cells * fade)[..., None]
        img += (CLOUD_COLOR - img) * alpha

    def _draw_water(self, img, dx, dy_row, dz, eye, t):
        # Distant, fogged and low-contrast, so it's shaded at half resolution
        # and doubled up -- the single biggest per-frame saving.
        R, W = dx.shape
        dx, dz, dy_row = dx[::2, ::2], dz[::2, ::2], dy_row[::2]
        tt = ((self.water_y - eye[1]) / np.minimum(dy_row, -1e-4))[:, None]
        bx = np.floor(eye[0] + tt * dx).astype(np.int32)
        bz = np.floor(eye[2] + tt * dz).astype(np.int32)
        # Per-block shade from a cheap integer hash (no table lookup), plus a
        # slow rolling wave so the surface isn't static.
        h = ((bx * 73856093) ^ (bz * 19349663)) & 1023
        shade = 0.95 + h * (0.1 / 1023) + 0.05 * np.sin(bx * 0.9 + bz * 0.6 + t * 1.8)
        fog = np.clip((tt - 10) / (FOG_END + 30 - 10), 0, 1)[..., None]
        col = shade[..., None] * (WATER_COLOR * (1 - fog)) + FOG_COLOR * fog
        img[:] = col.repeat(2, axis=0).repeat(2, axis=1)[:R, :W]

    def _draw_blocks(self, img, depth, D, eye, fwd, right, up):
        W, H, f = self.w, self.h, self.f
        rel = self.centers - eye.astype(np.float32)
        z = rel @ fwd
        dist = np.sqrt((rel * rel).sum(1))
        # View-cone cull (0.9 ~ a block's bounding radius), so off-screen
        # blocks never reach the per-face Python loop below.
        zc = np.maximum(z, 0)
        in_view = ((np.abs(rel @ right) <= zc * (W / 2 / f) + 0.9)
                   & (np.abs(rel @ up) <= zc * (H / 2 / f) + 0.9))
        visible = np.nonzero((dist < FOG_END + 2) & (z > -1.8) & in_view)[0]
        ex, ey, ez = (float(v) for v in eye)
        eye_l = (ex, ey, ez)

        for bi in visible:
            bx, by, bz = (int(v) for v in self.pos[bi])
            bmin = (bx, by, bz)
            for face in range(6):
                if not self.faces[bi, face]:
                    continue
                a, sign = FACE_AXIS[face], FACE_SIGN[face]
                plane = bmin[a] + (1 if sign > 0 else 0)
                # Back-face cull: the camera must be on the face's outer side.
                if (eye_l[a] - plane) * sign <= 0:
                    continue
                b_ax, c_ax = [ax for ax in (0, 1, 2) if ax != a]

                # Screen-space bounding box from the projected corners.
                full = False
                sxs, sys_ = [], []
                for cb in (0, 1):
                    for cc in (0, 1):
                        q = [0.0, 0.0, 0.0]
                        q[a] = plane
                        q[b_ax] = bmin[b_ax] + cb
                        q[c_ax] = bmin[c_ax] + cc
                        r = (q[0] - ex, q[1] - ey, q[2] - ez)
                        zc = r[0] * fwd[0] + r[1] * fwd[1] + r[2] * fwd[2]
                        if zc <= NEAR:
                            full = True
                            break
                        sxs.append((r[0] * right[0] + r[1] * right[1] + r[2] * right[2]) / zc * f + W / 2)
                        sys_.append(H / 2 - (r[0] * up[0] + r[1] * up[1] + r[2] * up[2]) / zc * f)
                    if full:
                        break
                if full:
                    x0, x1, y0, y1 = 0, W, 0, H
                else:
                    x0, x1 = max(int(min(sxs)), 0), min(int(max(sxs)) + 2, W)
                    y0, y1 = max(int(min(sys_)), 0), min(int(max(sys_)) + 2, H)
                    if x0 >= x1 or y0 >= y1:
                        continue

                sub = (slice(y0, y1), slice(x0, x1))
                Da = D[a][sub]
                with np.errstate(divide="ignore", invalid="ignore"):
                    tt = (plane - eye_l[a]) / Da
                fb = eye_l[b_ax] + tt * D[b_ax][sub] - bmin[b_ax]
                fc = eye_l[c_ax] + tt * D[c_ax][sub] - bmin[c_ax]
                dsub = depth[sub]
                m = ((tt > NEAR) & (tt < dsub) & (fb >= 0) & (fb < 1) & (fc >= 0) & (fc < 1))
                if not m.any():
                    continue

                fb, fc, tm = fb[m], fc[m], tt[m]
                if a == 1:          # top/bottom: u along x, v along z
                    u, v = fb, fc
                elif a == 0:        # x faces: others are (y, z)
                    u, v = fc, 1 - fb
                else:               # z faces: others are (x, y)
                    u, v = fb, 1 - fc
                ui = np.minimum((u * TEX).astype(np.int32), TEX - 1)
                vi = np.minimum((v * TEX).astype(np.int32), TEX - 1)
                col = self.atlas[self.types[bi], face][vi, ui]
                fog = np.clip((tm - FOG_START) / (FOG_END - FOG_START), 0, 1)[..., None]
                img[sub][m] = col * (1 - fog) + FOG_COLOR * fog
                dsub[m] = tm

    def _draw_arm(self, frame, t):
        """A plain blocky forearm in the lower-right corner, projected from a
        small 3D box in camera space so it has correct perspective."""
        bob = math.sin(t * 9.0) * 0.012
        base = np.array([0.40, -0.62 + bob, 0.58])
        tip = np.array([0.30, -0.47 + bob, 1.16])
        axis = (tip - base) / np.linalg.norm(tip - base)
        side = np.cross(axis, [0.0, 1.0, 0.0])
        side /= np.linalg.norm(side)
        upv = np.cross(side, axis)
        hw = 0.08
        corners = {}
        for i, end in enumerate((base, tip)):
            for j, s1 in enumerate((-1, 1)):
                for k, s2 in enumerate((-1, 1)):
                    corners[(i, j, k)] = end + side * s1 * hw + upv * s2 * hw
        quads = [  # (corner keys, outward normal, color)
            ([(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)], upv, (214, 164, 124)),
            ([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], -upv, (150, 108, 80)),
            ([(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)], -side, (184, 136, 100)),
            ([(0, 1, 0), (1, 1, 0), (1, 1, 1), (0, 1, 1)], side, (170, 124, 92)),
        ]
        draw = ImageDraw.Draw(frame)
        faces = []
        for keys, normal, color in quads:
            pts3 = [corners[k] for k in keys]
            center = np.mean(pts3, axis=0)
            if np.dot(normal, center) >= 0:  # facing away from the eye
                continue
            pts = [(p[0] / p[2] * self.f + self.w / 2, self.h / 2 - p[1] / p[2] * self.f) for p in pts3]
            faces.append((center[2], pts, color))
        for _, pts, color in sorted(faces, reverse=True):
            draw.polygon(pts, fill=color)


def build_background(total_duration, w, h, seed=None):
    """moviepy VideoClip of freshly generated parkour gameplay."""
    from moviepy.editor import VideoClip

    game = ParkourGameplay(total_duration, w, h, seed=seed)
    return VideoClip(game, duration=total_duration)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Render a standalone gameplay preview.")
    ap.add_argument("out", help="output .mp4 (or .png for a single frame)")
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--width", type=int, default=1080)
    ap.add_argument("--height", type=int, default=1920)
    args = ap.parse_args()

    if args.out.lower().endswith(".png"):
        g = ParkourGameplay(args.seconds, args.width, args.height, seed=args.seed)
        Image.fromarray(g(args.seconds / 2)).save(args.out)
    else:
        clip = build_background(args.seconds, args.width, args.height, seed=args.seed)
        clip.write_videofile(args.out, fps=30, codec="libx264", preset="veryfast", logger=None)
    print(f"wrote {args.out}")
