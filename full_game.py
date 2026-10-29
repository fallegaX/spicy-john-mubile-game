"""
SPICY JOHN: A Cultural Adventure  --  remastered  (5 CHAPTERS EDITION)
=======================================================================
Run:  python full_game.py          (debug: --fight --chapter=3 --char=jane)
Folder layout (next to this file):
    assets/images/*.png      (your images.rar)
    assets/sprite/*.png      (your sprite.rar  -> needed for Jane's death + John's smooth idle)
    assets/sounds/*          (your sounds; anything missing is replaced by built-in synth sounds)

CONTROLS (fight)
    Move ........ Arrows / A D          Jump ....... SPACE
    Light ....... Z or J  (tap to chain)  Heavy ..... X or K  (fireball / light orb)
    Special ..... C or L  (needs 50 energy)   Dash ..... LEFT SHIFT or V
    ULTIMATE .... R or Q  (needs full ULT meter - cinematic zoom attack!)
    Launcher .... UP + Light             Air slam ... DOWN + Light in the air
    Heavy variants: DOWN+X pillars | UP+X rising phoenix | DASH then X comet | X in air meteor shot
    Double jump . SPACE again in the air     Perfect dodge: dash through an attack -> slow motion
    Pause ....... ESC or P               Fullscreen . F11
"""
import pygame, sys, os, math, random, array, json, traceback
if __name__ == "__main__":                       # let `import full_game` (mobile_controls, online_scenes) reuse this module
    sys.modules.setdefault("full_game", sys.modules["__main__"])

# ---------------------------------------------------------------- mobile touch layer
IS_ANDROID = "ANDROID_ARGUMENT" in os.environ or "android" in sys.modules
try:
    from mobile_controls import TouchControls
    touch = TouchControls()
    touch.active = IS_ANDROID
except Exception:
    touch = None

pygame.mixer.pre_init(44100, -16, 2, 512)

pygame.init()
try:
    pygame.mixer.init()
except Exception:
    pass

W, H = 1920, 1080
FPS = 60
GROUND = 995                      # y of the "feet line" in the fight scene
GRAV = 1.3
FROZEN = getattr(sys, "frozen", False)                       # running as a PyInstaller .exe
BASE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(BASE, "assets")
# settings must live next to the .exe (the bundle folder is read-only / temporary)
SETTINGS_FILE = os.path.join(os.path.dirname(sys.executable) if FROZEN else BASE, "settings.json")

WHITE = (255, 255, 255); BLACK = (0, 0, 0); RED = (220, 40, 40); GREEN = (70, 220, 90)
GOLD = (255, 205, 60); ORANGE = (255, 140, 30); BLUE = (80, 170, 255); GREY = (150, 150, 150)

settings = {"music": 0.5, "sfx": 0.8, "fullscreen": False, "best": 0, "unlocked": 1}
try:
    with open(SETTINGS_FILE) as f:
        settings.update(json.load(f))
except Exception:
    pass


def save_settings():
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f)
    except Exception:
        pass


REAL = None                                   # Android only: the real display surface
FIT = (1.0, 0, 0, W, H)                       # scale, offset x, offset y, width, height of the letterboxed picture


def make_display(fullscreen=False):
    global REAL, FIT
    if IS_ANDROID:
        # Draw everything on a private 1920x1080 surface and letterbox it onto whatever the phone's screen is
        # (no SCALED / vsync flags: they crash on many Android devices).
        try:
            REAL = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        except Exception:
            REAL = pygame.display.set_mode((W, H))
        rw, rh = REAL.get_size()
        sc = min(rw / float(W), rh / float(H)); dw, dh = int(W * sc), int(H * sc)
        FIT = (sc, (rw - dw) // 2, (rh - dh) // 2, dw, dh)
        return pygame.Surface((W, H)).convert()
    flags = pygame.SCALED | pygame.RESIZABLE
    if fullscreen:
        flags |= pygame.FULLSCREEN
    try:
        return pygame.display.set_mode((W, H), flags, vsync=1)
    except Exception:
        return pygame.display.set_mode((W, H), flags)


def present(buf):
    """show the finished frame (Android: letterbox it, desktop: plain flip)"""
    if REAL is None:
        pygame.display.flip(); return
    sc, ox, oy, dw, dh = FIT
    if dw == W and dh == H: REAL.blit(buf, (ox, oy))
    else: REAL.blit(pygame.transform.scale(buf, (dw, dh)), (ox, oy))
    pygame.display.flip()


def to_game_xy(nx, ny):
    """normalised touch position (0..1 of the real screen) -> 1920x1080 game coordinates"""
    if REAL is None: return nx * W, ny * H
    sc, ox, oy, dw, dh = FIT; rw, rh = REAL.get_size()
    return (nx * rw - ox) / sc, (ny * rh - oy) / sc


screen = make_display(settings["fullscreen"])
pygame.display.set_caption("Spicy John: A Cultural Adventure")
clock = pygame.time.Clock()

# ----------------------------------------------------------------------------------------------
#  helpers
# ----------------------------------------------------------------------------------------------
def clamp(v, a, b): return a if v < a else b if v > b else v
def lerp(a, b, t): return a + (b - a) * t


_fonts = {}
def font(size, bold=False):
    k = (size, bold)
    if k not in _fonts:
        _fonts[k] = pygame.font.SysFont("impact,arialblack,arial,dejavusans", size, bold=bold)
    return _fonts[k]

_fonts_n = {}
def nfont(size, bold=False):
    k = (size, bold)
    if k not in _fonts_n:
        _fonts_n[k] = pygame.font.SysFont("arial,dejavusans,liberationsans", size, bold=bold)
    return _fonts_n[k]


def text(surf, s, f, color, pos, anchor="topleft", shadow=3, alpha=255, outline=0):
    img = f.render(str(s), True, color)
    r = img.get_rect(**{anchor: pos})
    if outline:
        o = f.render(str(s), True, (0, 0, 0))
        for dx in (-outline, 0, outline):
            for dy in (-outline, 0, outline):
                if dx or dy:
                    oo = o.copy(); oo.set_alpha(alpha); surf.blit(oo, r.move(dx, dy))
    elif shadow:
        sh = f.render(str(s), True, (0, 0, 0)); sh.set_alpha(min(alpha, 200))
        surf.blit(sh, r.move(shadow, shadow))
    if alpha < 255:
        img.set_alpha(alpha)
    surf.blit(img, r)
    return r


def wrap(s, f, maxw):
    words = s.split(" "); lines = []; cur = ""
    for w in words:
        t = (cur + " " + w).strip()
        if f.size(t)[0] <= maxw:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur: lines.append(cur)
    return lines


def rrect(surf, color, rect, r=14, width=0):
    pygame.draw.rect(surf, color, rect, width, border_radius=r)


# ----------------------------------------------------------------------------------------------
#  asset loading
# ----------------------------------------------------------------------------------------------
MISSING = []
_IMG_DIRS = ["images", os.path.join("images", "images"), "sprite", os.path.join("sprite", "sprite"), ""]

def find_asset(name, dirs=None, sub=None):
    for d in (dirs or _IMG_DIRS):
        p = os.path.join(ASSETS, d, name)
        if os.path.exists(p):
            return p
    # also try next to the script (flat layout)
    p = os.path.join(BASE, name)
    return p if os.path.exists(p) else None


def img(name, dirs=None, scale=None, smooth=True):
    p = find_asset(name, dirs)
    if not p:
        MISSING.append(name)
        s = pygame.Surface((64, 64), pygame.SRCALPHA); s.fill((255, 0, 255, 120))
        return s
    s = pygame.image.load(p).convert_alpha()
    if scale:
        sz = (int(s.get_width() * scale), int(s.get_height() * scale))
        s = pygame.transform.smoothscale(s, sz) if smooth else pygame.transform.scale(s, sz)
    return s


def cover(surf, size=(W, H)):
    """scale to cover the target size and crop the centre"""
    sw, sh = surf.get_size()
    sc = max(size[0] / sw, size[1] / sh)
    s = pygame.transform.smoothscale(surf, (int(sw * sc + 1), int(sh * sc + 1)))
    out = pygame.Surface(size).convert()
    out.blit(s, ((size[0] - s.get_width()) // 2, (size[1] - s.get_height()) // 2))
    return out


def frames_from_sheet(path_name, fw=128, dirs=None):
    p = find_asset(path_name, dirs)
    if not p:
        MISSING.append(path_name)
        return []
    s = pygame.image.load(p).convert_alpha()
    w, h = s.get_size()
    n = math.ceil(w / fw)
    out = []
    for i in range(n):
        f = pygame.Surface((fw, h), pygame.SRCALPHA)
        f.blit(s, (0, 0), (i * fw, 0, min(fw, w - i * fw), h))
        out.append(f)
    while out and out[-1].get_bounding_rect(8).w == 0:     # drop blank trailing frames
        out.pop()
    return out


def leg_cx(frame):
    """x-centre of the feet. Every sheet draws the body at a slightly different x, so we align on this."""
    h = frame.get_height()
    sub = frame.subsurface((0, h - 30, frame.get_width(), 30))
    m = pygame.mask.from_surface(sub, 8)
    if m.count() == 0:
        return frame.get_width() / 2
    return m.centroid()[0]


class Anim:
    """Pre-cropped, pre-scaled (nearest neighbour -> crisp pixels) animation with feet anchoring."""
    def __init__(self, frames, scale, ax, ay, fps=12, loop=True, tint=None):
        self.fps = fps; self.loop = loop; self.scale = scale
        self.data = []
        for f in frames:
            r = f.get_bounding_rect(8)
            if r.w == 0 or r.h == 0:
                self.data.append((pygame.Surface((1, 1), pygame.SRCALPHA), 0, 0)); continue
            sub = f.subsurface(r).copy()
            if tint:
                sub.fill(tint, special_flags=pygame.BLEND_RGB_ADD)
            surf = pygame.transform.scale(sub, (max(1, int(r.w * scale)), max(1, int(r.h * scale))))
            self.data.append((surf, int((r.x - ax) * scale), int((r.y - ay) * scale)))
        self.n = len(self.data)
        self._flip = {}; self._white = {}

    def get(self, i, flip=False):
        i = clamp(int(i), 0, self.n - 1)
        if not flip:
            return self.data[i]
        if i not in self._flip:
            s, ox, oy = self.data[i]
            self._flip[i] = (pygame.transform.flip(s, True, False), -(ox + s.get_width()), oy)
        return self._flip[i]

    def white(self, i, flip=False):
        k = (clamp(int(i), 0, self.n - 1), flip)
        if k not in self._white:
            s, ox, oy = self.get(i, flip)
            m = pygame.mask.from_surface(s, 8)
            self._white[k] = (m.to_surface(setcolor=(255, 255, 255, 255), unsetcolor=(0, 0, 0, 0)), ox, oy)
        return self._white[k]

    def draw(self, surf, i, x, y, cam=0, flip=False, white=False, alpha=255):
        s, ox, oy = self.white(i, flip) if white else self.get(i, flip)
        if alpha < 255:
            s = s.copy(); s.set_alpha(alpha)
        surf.blit(s, (int(x + ox - cam), int(y + oy)))


def make_anim(name, scale, fps=12, loop=True, align="first", fw=128, rng=None, tint=None, dirs=None,
              center=False, fh=None):
    frames = frames_from_sheet(name, fw, dirs)
    if rng: frames = frames[rng[0]:rng[1] + 1]
    if not frames:                                                  # keep the game alive if an asset is missing
        s = pygame.Surface((fw, fh or 128), pygame.SRCALPHA); pygame.draw.rect(s, (255, 0, 255), (40, 40, 40, 80))
        frames = [s]
    if center:
        ax = frames[0].get_width() / 2; ay = frames[0].get_height() / 2
    else:
        ay = frames[0].get_height()
        if align == "median":
            xs = sorted(leg_cx(f) for f in frames); ax = xs[len(xs) // 2]
        else:
            ax = leg_cx(frames[0])
    return Anim(frames, scale, ax, ay, fps, loop, tint)


# ----------------------------------------------------------------------------------------------
#  audio  (your .wav/.mp3 files are used when present, otherwise tiny synthesized sfx)
# ----------------------------------------------------------------------------------------------
def synth(f0, f1, dur, vol=0.4, noise=0.0, decay=2.5):
    sr = 44100; n = int(sr * dur); buf = array.array("h"); ph = 0.0
    for i in range(n):
        t = i / n; f = f0 + (f1 - f0) * t; ph += 2 * math.pi * f / sr
        s = math.sin(ph) * (1 - noise) + random.uniform(-1, 1) * noise
        v = int(s * ((1 - t) ** decay) * vol * 32767)
        buf.append(v); buf.append(v)
    return pygame.mixer.Sound(buffer=buf.tobytes())


class Audio:
    SYN = {"swing": (800, 260, .12, .35, .55, 2), "hit": (190, 60, .14, .6, .5, 3), "heavy": (120, 40, .26, .7, .45, 2.5),
           "fire": (260, 900, .32, .35, .3, 2), "special": (90, 700, .7, .5, .25, 1.4), "jump": (320, 640, .12, .3, 0, 2),
           "dash": (950, 200, .16, .3, .8, 2), "pickup": (600, 1300, .18, .35, 0, 1.5), "hurt": (260, 90, .22, .55, .3, 2),
           "hover": (900, 1000, .04, .25, 0, 1), "confirm": (500, 950, .14, .35, 0, 1.5), "true": (660, 990, .25, .4, 0, 1.2),
           "false": (200, 110, .35, .45, .2, 1.5), "boom": (95, 30, .55, .8, .5, 1.8), "ko": (300, 40, .9, .7, .3, 1.2),
           "slam": (140, 35, .4, .8, .5, 2), "wave": (200, 600, .3, .4, .4, 1.5), "place": (420, 300, .08, .4, 0, 2),
           "tick": (1200, 1200, .03, .15, 0, 1)}
    FILES = {"attack": "attack.wav", "hit": "hit.wav", "hover": "puzzle.wav", "true": "true.mp3", "false": "false.mp3",
             "place": "puzzle.wav"}

    def __init__(self):
        self.ok = pygame.mixer.get_init() is not None
        self.cache = {}; self.cur = None
        if self.ok:
            pygame.mixer.set_num_channels(24)

    def _find(self, fn):
        base, ext = os.path.splitext(fn)
        names = [base + ".ogg", fn] if ext.lower() == ".mp3" else [fn]       # music ships as .ogg (small + works on Android)
        for d in ("sounds", "sound", ""):
            for nm in names:
                p = os.path.join(ASSETS, d, nm)
                if os.path.exists(p): return p
        return None

    def get(self, name):
        if not self.ok: return None
        if name in self.cache: return self.cache[name]
        snd = None
        fn = self.FILES.get(name, name + ".wav")
        p = self._find(fn)
        try:
            if p: snd = pygame.mixer.Sound(p)
        except Exception:
            snd = None
        if snd is None:
            key = {"attack": "swing"}.get(name, name)
            if key in self.SYN:
                try: snd = synth(*self.SYN[key])
                except Exception: snd = None
        self.cache[name] = snd
        return snd

    def play(self, name, vol=1.0):
        s = self.get(name)
        if s:
            s.set_volume(clamp(vol * settings["sfx"], 0, 1)); s.play()

    def music(self, fn, loop=True, vol=1.0):
        if not self.ok: return
        if self.cur == fn and pygame.mixer.music.get_busy(): return
        p = self._find(fn)
        if not p:
            self.cur = None; pygame.mixer.music.stop(); return
        try:
            pygame.mixer.music.load(p); pygame.mixer.music.set_volume(settings["music"] * vol)
            pygame.mixer.music.play(-1 if loop else 0); self.cur = fn
        except Exception:
            self.cur = None

    def stop(self):
        if self.ok: pygame.mixer.music.stop()
        self.cur = None

    def refresh(self):
        if self.ok: pygame.mixer.music.set_volume(settings["music"])


audio = Audio()


# ----------------------------------------------------------------------------------------------
#  tiny particle / text effects
# ----------------------------------------------------------------------------------------------
class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max", "color", "size", "grav", "glow")
    def __init__(self, x, y, vx, vy, life, color, size, grav=0.3, glow=False):
        self.x = x; self.y = y; self.vx = vx; self.vy = vy; self.life = self.max = life
        self.color = color; self.size = size; self.grav = grav; self.glow = glow


class FloatText:
    def __init__(self, s, x, y, color, size=44, life=50, vy=-1.6, outline=3):
        self.s = s; self.x = x; self.y = y; self.color = color; self.size = size
        self.life = self.max = life; self.vy = vy; self.outline = outline


class Effects:
    def __init__(self):
        self.parts = []; self.texts = []; self.rings = []; self.sprites = []; self.shake = 0.0
        self.flash = 0.0; self.flash_color = WHITE; self.slashes = []; self.zoom_kick = 0.0

    def burst(self, x, y, n=12, colors=((255, 220, 90), (255, 140, 30), (255, 255, 255)), speed=9, size=(4, 9), life=(14, 28), grav=0.35, glow=True):
        for _ in range(n):
            a = random.uniform(0, math.tau); v = random.uniform(speed * .3, speed)
            self.parts.append(Particle(x, y, math.cos(a) * v, math.sin(a) * v - 2, random.randint(*life),
                                       random.choice(colors), random.uniform(*size), grav, glow))

    def dust(self, x, y, n=8, dirn=0):
        for _ in range(n):
            self.parts.append(Particle(x + random.uniform(-30, 30), y - 6, random.uniform(-3, 3) + dirn * 2, random.uniform(-2.5, -.3),
                                       random.randint(18, 34), (225, 190, 130), random.uniform(6, 14), -0.02))

    def ring(self, x, y, r, color=(255, 200, 80), life=24, width=10, flat=0.35):
        self.rings.append([x, y, 10, r, life, life, color, width, flat])

    def text(self, s, x, y, color=WHITE, size=44, life=50, vy=-1.6):
        for _ in range(6):                      # nudge up so pop-ups never overlap
            if any(abs(t.x - x) < 420 and abs(t.y - y) < size * 1.1 and t.life > t.max * .35 for t in self.texts): y -= size * 1.1
            else: break
        self.texts.append(FloatText(s, x, y, color, size, life, vy))

    def sprite(self, anim, x, y, fps=14, flip=False, frames=None, alpha=255):
        self.sprites.append([anim, x, y, 0, fps, flip, frames, alpha])

    def boom(self, name, x, y, scale=2.0, fps=18, anchor="center", fw=256, flip=False, alpha=255, rng=None):
        """play one of the explosion / lightning / fire sheets from assets/fx"""
        self.sprite(fx_anim(name, scale, fps, anchor, fw, rng), x, y, fps, flip, None, alpha)

    def slash(self, x, y, face, size=220, color=(255, 255, 255), life=9, tilt=0.0):
        self.slashes.append([x, y, face, size, life, life, color, tilt])

    def update(self, world=True, screen=True):
        if world:
            for p in self.parts:
                p.x += p.vx; p.y += p.vy; p.vy += p.grav; p.vx *= 0.97; p.life -= 1
            self.parts = [p for p in self.parts if p.life > 0]
            for t in self.texts:
                t.y += t.vy; t.vy *= 0.97; t.life -= 1
            self.texts = [t for t in self.texts if t.life > 0]
            for r in self.rings:
                r[4] -= 1
            self.rings = [r for r in self.rings if r[4] > 0]
            for s in self.sprites:
                s[3] += 1
            self.sprites = [s for s in self.sprites if int(s[3] * s[4] / FPS) < (s[6] if s[6] else s[0].n)]
            for sl in self.slashes:
                sl[4] -= 1
            self.slashes = [sl for sl in self.slashes if sl[4] > 0]
        if screen:
            self.shake *= 0.86
            if self.shake < 0.3: self.shake = 0
            self.flash *= 0.85
            self.zoom_kick *= 0.88
            if self.zoom_kick < 0.002: self.zoom_kick = 0.0

    def draw_world(self, surf, cam):
        for r in self.rings:
            x, y, r0, r1, life, mx, col, wd, flat = r
            t = 1 - life / mx; rad = lerp(r0, r1, 1 - (1 - t) ** 2)
            rect = pygame.Rect(0, 0, rad * 2, rad * 2 * flat); rect.center = (x - cam, y)
            ring = pygame.Surface((rect.w + 4, rect.h + 4), pygame.SRCALPHA)
            pygame.draw.ellipse(ring, (*col, int(230 * (1 - t))), ring.get_rect(), max(2, int(wd * (1 - t))))
            surf.blit(ring, (rect.x - 2, rect.y - 2))
        for s in self.sprites:
            anim, x, y, t, fps, flip, frames, alpha = s
            anim.draw(surf, int(t * fps / FPS), x, y, cam, flip, alpha=alpha)
        for sl in self.slashes:
            x, y, face, R, life, mx, col, tilt = sl
            prog = 1 - life / mx; sweep = min(1.0, prog * 2.4)
            a0 = -72.0; a1 = a0 + 150.0 * sweep; steps = 10; po = []; pi_ = []
            for k in range(steps + 1):
                a = math.radians(a0 + (a1 - a0) * k / steps + tilt)
                po.append((math.cos(a) * R, math.sin(a) * R))
                pi_.append((math.cos(a) * R * 0.74 - R * 0.14, math.sin(a) * R * 0.74))
            S = int(R * 2.4); c0 = S // 2
            tmp = pygame.Surface((S, S), pygame.SRCALPHA)
            al = int(235 * max(0.0, 1 - prog) ** 0.7)
            pts = [(c0 + px * face, c0 + py) for px, py in po + pi_[::-1]]
            pygame.draw.polygon(tmp, (*col, al), pts)
            surf.blit(tmp, (x - cam - c0, y - c0))
        for p in self.parts:
            a = p.life / p.max; sz = max(1, int(p.size * (0.4 + 0.6 * a)))
            if p.glow:
                pygame.draw.circle(surf, p.color, (int(p.x - cam), int(p.y)), sz)
            else:
                g = pygame.Surface((sz * 2, sz * 2), pygame.SRCALPHA)
                pygame.draw.circle(g, (*p.color, int(150 * a)), (sz, sz), sz)
                surf.blit(g, (p.x - cam - sz, p.y - sz))

    def draw_texts(self, surf, cam):
        for t in self.texts:
            a = int(255 * min(1, t.life / (t.max * .5)))
            text(surf, t.s, font(t.size), t.color, (t.x - cam, t.y), "center", alpha=a, outline=t.outline)

# ==============================================================================================
#  CHARACTER ART  (built lazily, after the display exists)
# ==============================================================================================
PS = 4.0                           # player sprite scale  (was 1.0 -> characters are now 4x bigger)
_ART = {}


def player_art(char):
    k = ("p", char)
    if k in _ART: return _ART[k]
    if char == "john":
        idle = make_anim("idle.png", PS, dirs=["sprite", "sprite/sprite", "images"])
        if idle.n <= 1: idle = make_anim("john_idle.png", PS)
        dead = make_anim("Dead.png", PS, dirs=["images", "images/images"])
        A = dict(idle=idle, run=make_anim("john_run.png", PS, align="median"), jump=make_anim("john_jump.png", PS),
                 atk1=make_anim("Attack.png", PS), atk=make_anim("john_attack.png", PS), cast=make_anim("Recharge.png", PS),
                 hurt=make_anim("john_hurt.png", PS), dead=dead)
    else:
        jd = make_anim("jane_dead.png", PS)
        if jd.n <= 1 and "jane_dead.png" in MISSING:
            MISSING.remove("jane_dead.png")
            jd = make_anim("Dead.png", PS, dirs=["sprite", "sprite/sprite"])
        hurt_frames = frames_from_sheet("jane_jump.png")[1:2] * 4
        A = dict(idle=make_anim("jane_idle.png", PS), run=make_anim("jane_run.png", PS, align="median"),
                 jump=make_anim("jane_jump.png", PS), atk1=make_anim("444.png", PS), atk2=make_anim("Attack_1.png", PS),
                 atk=make_anim("jane_attack.png", PS), cast=make_anim("Light_ball.png", PS), dead=jd,
                 hurt=Anim(hurt_frames, PS, leg_cx(hurt_frames[0]), 128) if hurt_frames else make_anim("jane_idle.png", PS))
    _ART[k] = A
    return A


def fx_art():
    if "fx" in _ART: return _ART["fx"]
    def pair(name, fw, a, b, sc, hit_sc=None, h=None):
        fr = frames_from_sheet(name, fw)
        if not fr:
            s = pygame.Surface((fw, h or fw), pygame.SRCALPHA); pygame.draw.circle(s, (255, 160, 40), (fw // 2, fw // 2), 14); fr = [s] * 12
        cx, cy = fr[0].get_width() / 2, fr[0].get_height() / 2
        return (Anim(fr[a[0]:a[1] + 1], sc, cx, cy, 14), Anim(fr[b[0]:b[1] + 1], hit_sc or sc, cx, cy, 14))
    def fire_pair(R, tail, hit_sc, seed):
        fr, ax, ay = _fireball_frames(R, tail, seed=seed)
        return (GlowAnim(fr, ax, ay, 18, _halo(int(R * 2.3), (225, 70, 10), 115)), fx_anim("boom_round", hit_sc, 22))

    def thunder_pair(R, tail, hit_name, hit_sc, seed, pal):
        fr, ax, ay = _thunderball_frames(R, tail, seed=seed, **pal)
        return (GlowAnim(fr, ax, ay, 24, _halo(int(R * 2.5), tuple(int(c * .45) for c in pal["glow"]), 105)), fx_anim(hit_name, hit_sc, 24))

    BLUE = dict(glow=(50, 120, 255), mid=(140, 200, 255), core=(235, 245, 255), arc=(170, 215, 255))
    ELEC = dict(glow=(110, 160, 255), mid=(200, 222, 255), core=(255, 250, 205), arc=(195, 222, 255))
    d = dict(fire=fire_pair(24, 130, 1.3, 3), fire_big=fire_pair(42, 230, 2.4, 4),
             blue=thunder_pair(18, 90, "blue_circle", 1.2, 5, BLUE), blue_big=thunder_pair(30, 150, "blue_circle", 1.9, 6, BLUE),
             light=thunder_pair(22, 90, "impact", 2.2, 7, ELEC), light_big=thunder_pair(40, 150, "impact", 3.4, 8, ELEC))
    d["nova"] = Anim(frames_from_sheet("harissa.png", 64)[6:12] or [pygame.Surface((64, 64), pygame.SRCALPHA)], 9.0, 32, 32, 16)
    # procedural projectiles for the new enemies  (fly anim, impact anim)
    d["gas"] = (_orb(70, 70, (90, 230, 90), (225, 255, 200)), fx_anim("gas", 0.8, 18))
    d["gas_big"] = (_orb(130, 130, (80, 220, 80), (225, 255, 200)), fx_anim("gas", 1.7, 18))
    d["bullet"] = (_orb(64, 22, (255, 190, 60), (255, 255, 220)), fx_anim("boom_round", 0.7, 20))
    d["bullet_big"] = (_orb(110, 36, (255, 150, 40), (255, 255, 220)), fx_anim("boom_round", 1.3, 20))
    d["laser"] = (_orb(96, 26, (70, 210, 255), (230, 255, 255)), fx_anim("blue_circle", 0.9, 20))
    d["laser_big"] = (_orb(160, 46, (70, 200, 255), (240, 255, 255)), fx_anim("blue_circle", 1.7, 20))
    d["bolt"] = (_orb(110, 110, (170, 120, 255), (245, 235, 255)), fx_anim("blue_circle", 1.6, 20))
    _ART["fx"] = d
    return d


_FXC = {}
def fx_anim(name, scale, fps=18, anchor="center", fw=256, rng=None):
    """cached Anim from assets/fx/<name>.png  (anchor 'center' or 'bottom')"""
    k = (name, scale, anchor, fw, rng)
    if k in _FXC: return _FXC[k]
    fr = frames_from_sheet(name + ".png", fw, ["fx"])
    if rng: fr = fr[rng[0]:rng[1] + 1]
    if not fr:
        sf = pygame.Surface((fw, fw), pygame.SRCALPHA); pygame.draw.circle(sf, (255, 170, 60), (fw // 2, fw // 2), fw // 5); fr = [sf] * 6
    w, h = fr[0].get_size()
    a = Anim(fr, scale, w / 2, h / 2 if anchor == "center" else h, fps, False)
    _FXC[k] = a
    return a


def _orb(w, h, col, core, n=4):
    """glowing procedural projectile frames (used for bullets, lasers, gas, bolts)"""
    frames = []
    for k in range(n):
        sf = pygame.Surface((w, h), pygame.SRCALPHA)
        wob = (k % 2) * 2
        for i in range(6, 0, -1):
            rw = max(2, int(w * i / 6)); rh = max(2, int(h * i / 6))
            pygame.draw.ellipse(sf, (*col, min(255, 40 + 34 * (6 - i))), (w // 2 - rw // 2, h // 2 - rh // 2 + wob - 1, rw, rh))
        pygame.draw.ellipse(sf, (*core, 255), (w // 2 - w // 6, h // 2 - h // 5, max(2, w // 3), max(2, 2 * h // 5)))
        frames.append(sf)
    return Anim(frames, 1.0, w / 2, h / 2, 16)


# -- glowing fireball / thunder ball (procedural, additive blended) -----------------------------
class GlowAnim:
    """additive-blended procedural animation. Quacks like Anim for what Projectile needs."""
    def __init__(self, frames, ax, ay, fps=16, halo=None):
        self.frames = frames; self.n = len(frames); self.ax = ax; self.ay = ay; self.fps = fps; self.scale = 1.0
        self.halo = halo; self._flip = {}

    def draw(self, surf, i, x, y, cam=0, flip=False, white=False, alpha=255):
        i = int(i) % self.n; f = self.frames[i]
        if flip:
            if i not in self._flip: self._flip[i] = pygame.transform.flip(f, True, False)
            f = self._flip[i]; ox = -(f.get_width() - self.ax)
        else:
            ox = -self.ax
        if self.halo is not None:               # soft dark body so the glow also reads on bright backgrounds
            hs = self.halo
            surf.blit(hs, (int(x - cam - hs.get_width() / 2), int(y - hs.get_height() / 2)))
        surf.blit(f, (int(x - cam + ox), int(y - self.ay)), special_flags=pygame.BLEND_RGB_ADD)


def _radial(r, color, power=1.8):
    """opaque black surface with a soft radial gradient (blit it with BLEND_RGB_ADD)"""
    r = max(3, int(r)); s = pygame.Surface((r * 2, r * 2)); s.fill((0, 0, 0))
    steps = max(8, min(r, 30))
    for i in range(steps, 0, -1):
        k = (1 - i / steps) ** power
        pygame.draw.circle(s, (int(color[0] * k), int(color[1] * k), int(color[2] * k)), (r, r), max(1, int(r * i / steps)))
    return s


def _add(dst, src_s, cx, cy):
    dst.blit(src_s, (int(cx - src_s.get_width() / 2), int(cy - src_s.get_height() / 2)), special_flags=pygame.BLEND_RGB_ADD)


def _halo(r, col, amax):
    r = max(4, int(r)); s = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA); steps = max(8, min(r, 30))
    for i in range(steps, 0, -1):
        a = int(amax * (1 - i / steps) ** 1.5)
        pygame.draw.circle(s, (col[0], col[1], col[2], a), (r, r), max(1, int(r * i / steps)))
    return s


def _fireball_frames(R, tail, n=8, seed=3, hot=(255, 235, 170), mid=(255, 150, 40), low=(220, 50, 10)):
    """a comet of fire: bright head on the right, flickering flame tail to the left"""
    rng = random.Random(seed)
    w = int(tail + R * 3.4); h = int(R * 5.2); hx = w - R * 1.8; cy = h / 2
    out = []
    for k in range(n):
        s = pygame.Surface((w, h)); s.fill((0, 0, 0)); ph = k * math.tau / n
        m = 14
        for j in range(m, 0, -1):                                   # tail blobs, far end first
            t = j / m; x = hx - t * tail
            y = cy + math.sin(ph * 2 + t * 6.5) * R * .5 * t + rng.uniform(-1, 1) * R * .14 * t
            rad = R * (1.35 - 1.0 * t); f = (1 - t) ** 1.1
            c = tuple(int((low[q] * t + mid[q] * (1 - t)) * f * .85) for q in range(3))
            _add(s, _radial(rad * 1.6, c, 1.5), x, y)
        ts = pygame.Surface((max(2, w // 3), max(2, h // 3))); ts.fill((0, 0, 0))   # soft flame tongues
        for j in range(5):
            a = math.pi + rng.uniform(-.75, .75) + math.sin(ph + j) * .12
            L = R * rng.uniform(1.6, 2.8); wd = R * rng.uniform(.35, .6)
            tip = (hx + math.cos(a) * L, cy + math.sin(a) * L)
            nx, ny = -math.sin(a) * wd, math.cos(a) * wd
            bx, by = hx + math.cos(a) * R * .3, cy + math.sin(a) * R * .3
            pygame.draw.polygon(ts, (205, 85, 12), [((bx + nx) / 3, (by + ny) / 3), (tip[0] / 3, tip[1] / 3), ((bx - nx) / 3, (by - ny) / 3)])
        s.blit(pygame.transform.smoothscale(ts, (w, h)), (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        pul = 1 + .07 * math.sin(ph)
        _add(s, _radial(R * 2.7 * pul, (255, 95, 15), 1.7), hx, cy)
        _add(s, _radial(R * 1.7 * pul, mid, 1.3), hx, cy)
        _add(s, _radial(R * 1.05 * pul, hot, 1.0), hx, cy)
        for _ in range(7):                                          # embers
            ex = hx - rng.uniform(.3, 1.0) * tail; ey = cy + rng.uniform(-1, 1) * R * 1.3
            pygame.draw.circle(s, (255, int(150 + rng.uniform(0, 90)), 60), (int(ex), int(ey)), max(1, int(R * rng.uniform(.05, .13))))
        out.append(s)
    return out, hx, cy


def _thunderball_frames(R, tail, n=8, seed=7, glow=(90, 140, 255), mid=(170, 205, 255), core=(255, 252, 225), arc=(200, 225, 255)):
    """crackling electric orb: glowing core, jagged arcs in every direction, sparks streaming behind"""
    rng = random.Random(seed); reach = R * 3.3
    w = int(tail + reach * 2); h = int(reach * 2); hx = w - reach; cy = h / 2
    dim = tuple(int(c * .55) for c in glow)

    def bolt(s, x0, y0, x1, y1, segs, jit, wd):
        dx, dy = x1 - x0, y1 - y0; ln = math.hypot(dx, dy) or 1.0; nx, ny = -dy / ln, dx / ln
        pts = [(x0, y0)]
        for q in range(1, segs):
            f = q / segs; o = rng.uniform(-1, 1) * jit * (1 - abs(f - .5) * .6)
            pts.append((x0 + dx * f + nx * o, y0 + dy * f + ny * o))
        pts.append((x1, y1))
        pygame.draw.lines(s, dim, False, pts, wd + 4)
        pygame.draw.lines(s, arc, False, pts, wd + 1)
        pygame.draw.lines(s, (255, 255, 255), False, pts, max(1, wd - 1))

    out = []
    for k in range(n):
        s = pygame.Surface((w, h)); s.fill((0, 0, 0)); ph = k * math.tau / n
        pul = 1 + .08 * math.sin(ph * 2)
        _add(s, _radial(R * 3.0 * pul, glow, 1.7), hx, cy)
        _add(s, _radial(R * 1.9 * pul, mid, 1.4), hx, cy)
        for _ in range(6):                                          # crackling arcs
            a = rng.uniform(0, math.tau); r0 = R * .7; r1 = R * rng.uniform(2.0, 3.2)
            bolt(s, hx + math.cos(a) * r0, cy + math.sin(a) * r0, hx + math.cos(a) * r1, cy + math.sin(a) * r1, 5, R * .4, 2)
        for _ in range(3):                                          # streaks trailing behind
            L = tail * rng.uniform(.5, 1.0); yy = cy + rng.uniform(-.8, .8) * R
            bolt(s, hx - R * .6, yy, hx - L, yy + rng.uniform(-.6, .6) * R, 7, R * .35, 2)
        for _ in range(6):                                          # sparks
            ex = hx - rng.uniform(.2, 1.0) * tail; ey = cy + rng.uniform(-1, 1) * R * 1.4
            pygame.draw.circle(s, (255, 255, 255), (int(ex), int(ey)), max(1, int(R * .08)))
        _add(s, _radial(R * 1.15 * pul, core, 1.0), hx, cy)
        for q in range(3):                                          # orbiting beads
            a = ph + q * math.tau / 3
            pygame.draw.circle(s, (255, 255, 255), (int(hx + math.cos(a) * R * 1.35), int(cy + math.sin(a) * R * 1.35 * .8)), max(2, int(R * .14)))
        out.append(s)
    return out, hx, cy


# -- enemy sprite families (assets/enemies) ----------------------------------------------------
def _fam(**m): return m
FAMILIES = {
    "zombie1": _fam(idle="zombie1_idle", walk="zombie1_walk", run="zombie1_walk", jump="zombie1_walk", atk="zombie1_attack", a1="zombie1_attack",
                    a2="zombie1_attack", arrow="zombie1_attack", hurt="zombie1_hurt", dead="zombie1_dead"),
    "zombie2": _fam(idle="zombie2_idle", walk="zombie2_walk", run="zombie2_walk", jump="zombie2_walk", atk="zombie2_attack", a1="zombie2_attack",
                    a2="zombie2_attack", arrow="zombie2_attack", hurt="zombie2_hurt", dead="zombie2_dead"),
    "zombie3": _fam(idle="zombie3_idle", walk="zombie3_walk", run="zombie3_walk", jump="zombie3_walk", atk="zombie3_attack", a1="zombie3_attack",
                    a2="zombie3_attack", arrow="zombie3_attack", hurt="zombie3_hurt", dead="zombie3_dead"),
    "zombie4": _fam(idle="zombie4_idle", walk="zombie4_walk", run="zombie4_walk", jump="zombie4_walk", atk="zombie4_attack", a1="zombie4_attack",
                    a2="zombie4_attack", arrow="zombie4_attack", hurt="zombie4_hurt", dead="zombie4_dead"),
    "raider1": _fam(idle="raider1_idle", walk="raider1_walk", run="raider1_run", jump="raider1_jump", atk="raider1_shot", a1="raider1_attack_2",
                    a2="raider1_attack_1", arrow="raider1_shot", hurt="raider1_hurt", dead="raider1_dead"),
    "raider2": _fam(idle="raider2_idle", walk="raider2_walk", run="raider2_run", jump="raider2_jump", atk="raider2_shot_1", a1="raider2_attack",
                    a2="raider2_attack", arrow="raider2_shot_2", hurt="raider2_hurt", dead="raider2_dead"),
    "raider3": _fam(idle="raider3_idle", walk="raider3_walk", run="raider3_run", jump="raider3_jump", atk="raider3_attack_3", a1="raider3_attack_1",
                    a2="raider3_attack_2", arrow="raider3_attack_3", hurt="raider3_hurt", dead="raider3_dead"),
    "infantry": _fam(idle="infantryman_idle", walk="infantryman_walk", run="infantryman_walk", jump="infantryman_idle", atk="infantryman_shot_1",
                     a1="infantryman_attack_2", a2="infantryman_attack_2", arrow="infantryman_shot_2", hurt="infantryman_hurt", dead="infantryman_dead"),
    "swordsman": _fam(idle="swordsman_idle", walk="swordsman_idle", run="swordsman_idle", jump="swordsman_enabling", atk="swordsman_attack_4",
                      a1="swordsman_attack_3", a2="swordsman_attack_1", arrow="swordsman_attack_1", hurt="swordsman_hurt", dead="swordsman_dead"),
    "destroyer": _fam(idle="destroyer_idle", walk="destroyer_walk", run="destroyer_walk", jump="destroyer_idle", atk="destroyer_shot_1",
                      a1="destroyer_attack_2", a2="destroyer_attack_1", arrow="destroyer_shot_2", hurt="destroyer_hurt", dead="destroyer_dead"),
}
_ANC = {}


def family_art(fam, scale, tint):
    k = ("fam", fam, scale, tint)
    if k in _ART: return _ART[k]
    A = {}
    for key, name in FAMILIES[fam].items():
        al = "median" if key in ("run", "walk") else "first"
        ck = (name, scale, tint, al)
        if ck not in _ANC:
            _ANC[ck] = make_anim(name + ".png", scale, align=al, tint=tint, dirs=["enemies"])
        A[key] = _ANC[ck]
    _ART[k] = A
    return A


def enemy_art(cfg, scale):
    if cfg.get("fam"): return family_art(cfg["fam"], scale, cfg.get("tint"))
    return sith_art(cfg.get("tint"), scale)


def sith_art(tint, scale):
    k = ("e", tint, scale)
    if k in _ART: return _ART[k]
    kw = dict(tint=tint)
    A = dict(idle=make_anim("enemy_idle.png", scale, **kw), run=make_anim("enemy_run.png", scale, align="median", **kw),
             jump=make_anim("enemy_jump.png", scale, **kw), atk=make_anim("enemy_attack.png", scale, **kw),
             a1=make_anim("Attack_1 (2).png", scale, **kw), a2=make_anim("Attack_2 (2).png", scale, **kw),
             arrow=make_anim("Magic_arrow.png", scale, **kw), hurt=make_anim("Hurt.png", scale, **kw),
             dead=make_anim("Dead (2).png", scale, **kw), walk=make_anim("Walk (2).png", scale, align="median", **kw))
    _ART[k] = A
    return A


# ==============================================================================================
#  MOVES   (all distances are screen pixels, frame indexes are relative to the 'frames' range)
# ==============================================================================================
def M(**k): return k

JOHN_MOVES = {
    "L1": M(anim="atk1", frames=(0, 4), fps=19, active=(2, 3), dmg=8, rx=(0, 175), ry=(-215, -40), kb=(7, 0), stun=16, stop=3,
            cancel=3, lunge=(5, 8), sfx="attack", shake=2),
    "L2": M(anim="atk", frames=(0, 7), fps=26, active=(4, 6), dmg=11, rx=(0, 245), ry=(-235, -30), kb=(9, 0), stun=18, stop=4,
            cancel=6, lunge=(4, 12), sfx="fire", shake=3),
    "L3": M(anim="jump", frames=(3, 8), fps=15, active=(1, 3), dmg=15, rx=(0, 240), ry=(-270, -20), kb=(18, -10), launch=True, stop=7,
            cancel=99, lunge=(14, 18), sfx="heavy", shake=9, name="FLYING KICK"),
    "UP": M(anim="jump", frames=(1, 6), fps=16, active=(2, 4), dmg=10, rx=(-30, 150), ry=(-350, -20), kb=(4, -26), launch=True, stop=5,
            cancel=99, self_vy=-25, sfx="heavy", shake=5, name="LAUNCHER", air=True),
    "AIR": M(anim="atk1", frames=(0, 4), fps=20, active=(2, 3), dmg=8, rx=(0, 190), ry=(-240, -5), kb=(4, -9), stun=22, stop=3,
             cancel=3, juggle=True, floaty=0.35, sfx="attack", shake=2),
    "SLAM": M(anim="jump", frames=(7, 8), fps=6, active=(0, 99), dmg=12, rx=(-70, 110), ry=(-30, 150), kb=(8, 18), launch=True, stop=6,
              cancel=99, slam=True, sfx="heavy", shake=6, name="DIVE SLAM"),
    "DASH": M(anim="atk1", frames=(0, 4), fps=19, active=(1, 3), dmg=12, rx=(0, 220), ry=(-225, -20), kb=(14, -9), launch=True, stop=5,
              cancel=99, lunge=(15, 10), sfx="heavy", shake=5, name="SPICY RUSH"),
    "HEAVY": M(anim="atk", frames=(0, 9), fps=20, active=(99, 99), dmg=0, cancel=99, sfx="fire",
               proj=dict(idx=5, kind="fire", dmg=16, speed=16, kb=(9, -5), stun=20, y=-130, x=95)),
    "FINISHER": M(anim="atk", frames=(0, 9), fps=24, active=(99, 99), dmg=0, cancel=99, sfx="boom", name="COMBO BREAKER",
                  proj=dict(idx=5, kind="fire_big", dmg=30, speed=18, kb=(16, -16), stun=30, y=-130, x=95, pierce=True, launch=True)),
    "SPECIAL": M(anim="cast", frames=(0, 5), fps=11, active=(99, 99), dmg=0, cancel=99, sfx="special", name="HARISSA NOVA", invuln=True,
                 nova=dict(idx=4, dmg=34, radius=420, kb=(16, -24))),
    # ---- new in the 5-chapter edition -------------------------------------------------------
    "PILLARS": M(anim="atk", frames=(0, 9), fps=20, active=(99, 99), dmg=0, cancel=99, sfx="special", name="SPICE PILLARS", cd=150, shake=4,
                 pillars=dict(idx=4, n=4, first=190, gap=190, delay=7, dmg=13, r=125, kind="fire")),
    "PHOENIX": M(anim="jump", frames=(1, 6), fps=15, active=(1, 4), dmg=15, rx=(-90, 235), ry=(-440, -10), kb=(5, -31), launch=True, stop=7,
                 cancel=99, self_vy=-29, sfx="heavy", shake=9, name="RISING PHOENIX", cd=80, trail=(255, 150, 40), burst="fire"),
    "COMET": M(anim="jump", frames=(3, 8), fps=11, active=(0, 99), dmg=8, rx=(-20, 250), ry=(-240, -10), kb=(7, -6), stun=18, stop=2,
               cancel=99, lunge=(27, 24), rehit=5, invuln=True, sfx="dash", shake=3, name="COMET CHARGE", cd=110, ghost=True,
               endboom=dict(radius=270, dmg=22, kind="fire")),
    "AIRHEAVY": M(anim="atk", frames=(0, 9), fps=24, active=(99, 99), dmg=0, cancel=99, sfx="fire", name="METEOR SHOT", cd=45, floaty=0.25,
                  proj=dict(idx=4, kind="fire_big", dmg=15, speed=12, vy=13, kb=(8, -8), stun=22, y=-150, x=80, aoe=240, launch=True)),
}

JANE_MOVES = {
    "L1": M(anim="atk1", frames=(0, 3), fps=16, active=(1, 2), dmg=7, rx=(0, 210), ry=(-225, -30), kb=(6, 0), stun=14, stop=3,
            cancel=2, lunge=(6, 8), sfx="attack", shake=2),
    "L2": M(anim="atk2", frames=(0, 9), fps=28, active=(3, 6), dmg=10, rx=(0, 250), ry=(-245, -20), kb=(8, 0), stun=16, stop=4,
            cancel=6, lunge=(4, 12), sfx="attack", shake=3),
    "L3": M(anim="cast", frames=(0, 6), fps=15, active=(2, 4), dmg=14, rx=(0, 270), ry=(-255, -20), kb=(18, -12), launch=True, stop=7,
            cancel=99, lunge=(9, 12), sfx="heavy", shake=8, name="LIGHT BURST"),
    "UP": M(anim="jump", frames=(1, 6), fps=16, active=(2, 4), dmg=9, rx=(-30, 150), ry=(-350, -20), kb=(4, -26), launch=True, stop=5,
            cancel=99, self_vy=-25, sfx="heavy", shake=5, name="LAUNCHER", air=True),
    "AIR": M(anim="atk1", frames=(0, 3), fps=17, active=(1, 2), dmg=7, rx=(0, 200), ry=(-245, -5), kb=(4, -9), stun=22, stop=3,
             cancel=2, juggle=True, floaty=0.35, sfx="attack", shake=2),
    "SLAM": M(anim="jump", frames=(6, 7), fps=6, active=(0, 99), dmg=11, rx=(-70, 110), ry=(-30, 150), kb=(8, 18), launch=True, stop=6,
              cancel=99, slam=True, sfx="heavy", shake=6, name="DIVE SLAM"),
    "DASH": M(anim="atk1", frames=(0, 3), fps=16, active=(1, 2), dmg=11, rx=(0, 230), ry=(-230, -20), kb=(14, -9), launch=True, stop=5,
              cancel=99, lunge=(15, 10), sfx="attack", shake=5, name="SPICY RUSH"),
    "HEAVY": M(anim="atk", frames=(0, 6), fps=22, active=(99, 99), dmg=0, cancel=99, sfx="fire",
               proj=dict(idx=4, kind="light", dmg=15, speed=19, kb=(8, -4), stun=18, y=-130, x=110)),
    "FINISHER": M(anim="atk", frames=(0, 6), fps=24, active=(99, 99), dmg=0, cancel=99, sfx="boom", name="COMBO BREAKER",
                  proj=dict(idx=4, kind="light_big", dmg=28, speed=21, kb=(16, -16), stun=30, y=-130, x=110, pierce=True, launch=True)),
    "SPECIAL": M(anim="atk", frames=(0, 11), fps=14, active=(4, 10), dmg=6, rx=(30, 620), ry=(-210, -40), kb=(7, -3), stun=14, stop=1,
                 cancel=99, rehit=6, sfx="special", name="SOLAR BEAM", special=True, shake=4),
    "PILLARS": M(anim="atk", frames=(0, 6), fps=18, active=(99, 99), dmg=0, cancel=99, sfx="special", name="LIGHT PILLARS", cd=150, shake=4,
                 pillars=dict(idx=3, n=4, first=190, gap=190, delay=7, dmg=13, r=125, kind="bolt")),
    "PHOENIX": M(anim="jump", frames=(1, 6), fps=15, active=(1, 4), dmg=14, rx=(-90, 235), ry=(-440, -10), kb=(5, -31), launch=True, stop=7,
                 cancel=99, self_vy=-29, sfx="heavy", shake=9, name="SOLAR ASCENT", cd=80, trail=(255, 245, 160), burst="light"),
    "COMET": M(anim="jump", frames=(3, 7), fps=11, active=(0, 99), dmg=7, rx=(-20, 260), ry=(-240, -10), kb=(7, -6), stun=18, stop=2,
               cancel=99, lunge=(29, 22), rehit=5, invuln=True, sfx="dash", shake=3, name="SOLAR DASH", cd=110, ghost=True,
               endboom=dict(radius=270, dmg=21, kind="light")),
    "AIRHEAVY": M(anim="atk", frames=(0, 6), fps=22, active=(99, 99), dmg=0, cancel=99, sfx="fire", name="STAR SHOT", cd=45, floaty=0.25,
                  proj=dict(idx=4, kind="light_big", dmg=14, speed=13, vy=13, kb=(8, -8), stun=22, y=-150, x=90, aoe=240, launch=True)),
}
MOVES = {"john": JOHN_MOVES, "jane": JANE_MOVES}
STATS = {"john": dict(name="JOHN", hp=300, speed=7.0, dmg=1.10, desc="Tough fighter. Harissa fire palms & fireballs."),
         "jane": dict(name="JANE", hp=240, speed=7.8, dmg=1.0, desc="Fast swordswoman. Light burst & solar beam.")}
SPECIAL_COST = 50
JUMP_V = 27


# ==============================================================================================
#  PLAYER
# ==============================================================================================
class Player:
    def __init__(self, char, blessing=1.0, energy=0):
        self.char = char; self.A = player_art(char); self.MV = MOVES[char]; st = STATS[char]
        self.name = st["name"]; self.maxhp = st["hp"]; self.hp = self.maxhp; self.speed = st["speed"]
        self.dmg_mult = st["dmg"] * blessing
        self.energy = float(energy); self.x = 400.0; self.y = float(GROUND); self.vx = 0.0; self.vy = 0.0; self.face = 1
        self.state = "idle"; self.t = 0; self.move = None; self.mname = ""; self.mt = 0; self.hit_ids = {}
        self.spawned = False; self.novaed = False; self.connected = False; self.popup_done = False
        self.chain = -1; self.chain_t = 99; self.buf = None; self.buf_t = 0
        self.invuln = 0; self.flash = 0; self.dash_t = 0; self.dash_cd = 0; self.dash_recent = 0
        self.hurt_t = 0; self.down_t = 0; self.dead_t = 0; self.slam = False; self.hist = []
        self.ghosts = []; self.hp_trail = float(self.hp); self.on_ground = True
        self.ult_meter = 0.0; self.ult_t = 0; self.air_jumps = 1; self.pd_cd = 0; self.cds = {}; self.pil_done = False
        self.pid = 1; self.tag = None          # multiplayer: player number + floating "P1/P2" marker

    # -- geometry ---------------------------------------------------------------------------
    def revive(self, frac=.5, x=None):
        self.hp = max(1, int(self.maxhp * frac)); self.hp_trail = float(self.hp); self.state = "idle"; self.t = 0; self.move = None
        self.vx = 0.0; self.vy = 0.0; self.y = float(GROUND); self.on_ground = True; self.invuln = 150; self.flash = 0; self.slam = False
        self.dead_t = 0; self.down_t = 0; self.hurt_t = 0; self.buf = None; self.chain = -1; self.hit_ids = {}
        if x is not None: self.x = float(x)

    def hurtbox(self): return pygame.Rect(int(self.x - 38), int(self.y - 212), 76, 212)

    def attack_rect(self, mv):
        a, b = mv["rx"]; t, bt = mv["ry"]
        x0 = self.x + a if self.face > 0 else self.x - b
        return pygame.Rect(int(x0), int(self.y + t), int(b - a), int(bt - t))

    # -- helpers ----------------------------------------------------------------------------
    def can_act(self): return self.state in ("idle", "run", "jump")

    def start_move(self, fight, name, held):
        mv = self.MV[name]
        was_dash = self.state == "dash" or self.dash_recent > 0
        self.move = mv; self.mname = name; self.mt = 0; self.state = "attack"; self.t = 0
        self.hit_ids = {}; self.spawned = False; self.novaed = False; self.connected = False; self.popup_done = False
        self.buf = None; self.slam = bool(mv.get("slam")); self.pil_done = False
        if mv.get("cd"): self.cds[name] = mv["cd"]
        if name in ("L1", "L2", "L3"): self.chain = int(name[1]) - 1
        self.hist.append((name, fight.tick)); self.hist = [h for h in self.hist if fight.tick - h[1] < 150][-5:]
        # face the nearest enemy if no direction held
        if not (held["left"] or held["right"]) and self.on_ground:
            e = fight.nearest_enemy(self.x, 420)
            if e: self.face = 1 if e.x >= self.x else -1
        if mv.get("self_vy"): self.vy = mv["self_vy"]; self.on_ground = False
        if mv.get("slam"): self.vy = 30; self.vx = 0
        if mv.get("invuln"): self.invuln = max(self.invuln, 40)
        if mv.get("sfx"): audio.play(mv["sfx"], .9)
        if name == "SPECIAL": self.energy -= SPECIAL_COST
        if name == "DASH": self.dash_t = 0; self.vx = 0
        self.popup = None
        names = [h[0] for h in self.hist]
        if name == "L3" and names[-3:] == ["L1", "L2", "L3"]: self.popup = ("TRIPLE STRIKE", 150)
        elif name == "UP" and names[-3:-1] == ["L1", "L2"]: self.popup = ("SKY BREAKER", 200)
        elif name == "AIR" and names[-3:] == ["UP", "AIR", "AIR"]: self.popup = ("AERIAL RAVE", 300)
        elif name == "SLAM" and "UP" in names[-4:]: self.popup = ("METEOR SPICE", 400)
        elif name == "PILLARS" and names[-4:-1] == ["L1", "L2", "L3"]: self.popup = ("INFERNO CROSS", 350)
        elif name == "AIRHEAVY" and names[-4:-1] == ["UP", "AIR", "AIR"]: self.popup = ("SKYFALL BLAST", 400)
        elif name == "AIR" and len(names) > 1 and names[-2] == "PHOENIX": self.popup = ("PHOENIX RAVE", 300)
        elif name == "PHOENIX" and names[-3:-1] == ["L1", "L2"]: self.popup = ("PHOENIX COMBO", 250)
        elif name == "COMET" and was_dash: self.popup = ("DASH COMET", 220)
        elif name == "FINISHER" and len(names) > 1 and names[-2] == "COMET": self.popup = ("COMET FINISH", 350)
        elif mv.get("name"): self.popup = (mv["name"], 100)
        # visuals that start with the move
        col = (255, 205, 120) if self.char == "john" else (175, 225, 255)
        if (mv.get("rx") and mv.get("dmg", 0) > 0 and not mv.get("lunge") and not mv.get("special")) or name in ("L1", "L2", "L3", "DASH"):
            a, b = mv["rx"]; dl = min(18, int(mv["active"][0] * FPS / mv["fps"]))
            sx = self.x + self.face * (a + (b - a) * .45); sy = self.y - 125
            tilt = {"L1": 0, "L2": 22, "L3": -25, "UP": -80, "AIR": 15, "DASH": 0, "PHOENIX": -85}.get(name, 0)
            fight.later(dl, lambda sx=sx, sy=sy, f=self.face, sz=(b - a) * .6 + 70, t=tilt: fight.fx.slash(sx, sy, f, sz, col, 9, t))
        if mv.get("burst"):
            fight.fx.boom("boom_ground" if mv["burst"] == "fire" else "blue_circle", self.x, self.y - 70, 2.1, 20)
            fight.fx.ring(self.x, self.y - 12, 260, col, 22, 12); fight.fx.zoom_kick = max(fight.fx.zoom_kick, .03)
        if name == "COMET": fight.fx.dust(self.x, self.y, 12, -self.face)

    def try_input(self, fight, kind, held):
        """returns True when the input was consumed"""
        if self.state in ("hurt", "down", "dead", "ult"): return False
        air = not self.on_ground
        if kind == "ult":
            return fight.try_ult(self)
        if kind == "jump":
            if self.on_ground and (self.can_act() or self.cancelable()):
                self.vy = -JUMP_V; self.on_ground = False; self.state = "jump"; self.move = None; self.t = 0
                audio.play("jump", .6); fight.fx.dust(self.x, self.y, 8); return True
            if (not self.on_ground) and self.air_jumps > 0 and (self.state == "jump" or self.cancelable()):
                self.air_jumps -= 1; self.vy = -JUMP_V * .92; self.state = "jump"; self.move = None; self.t = 0; self.slam = False
                audio.play("jump", .7); fight.fx.ring(self.x, self.y - 20, 150, (200, 230, 255), 16, 8, 0.4)
                fight.fx.burst(self.x, self.y - 10, 8, ((220, 240, 255), (255, 255, 255)), 6, (3, 6), (10, 18), 0.1, True)
                fight.fx.text("DOUBLE JUMP", self.x, self.y - 250, (200, 235, 255), 30, 28); return True
            return False
        if kind == "dash":
            if self.dash_cd <= 0 and (self.can_act() or self.cancelable()):
                self.state = "dash"; self.move = None; self.dash_t = 14; self.dash_cd = 28; self.invuln = max(self.invuln, 14)
                d = (1 if held["right"] else -1 if held["left"] else self.face); self.face = d; self.vx = d * 26
                if air: self.vy = min(self.vy, -3)
                audio.play("dash", .7); fight.fx.dust(self.x, self.y, 10, -d); return True
            return False
        # attacks need a free state or a cancel window
        if not (self.can_act() or self.cancelable() or self.state == "dash"): return False
        if kind == "special":
            if self.energy >= SPECIAL_COST and self.on_ground:
                self.start_move(fight, "SPECIAL", held); return True
            if self.energy < SPECIAL_COST: fight.fx.text("NEED ENERGY", self.x, self.y - 260, (120, 190, 255), 34, 30)
            return False
        if kind == "heavy":
            self.start_move(fight, self.pick_heavy(fight, held), held); return True
        if kind == "light":
            if air:
                if held["down"]: self.start_move(fight, "SLAM", held)
                else: self.start_move(fight, "AIR", held)
                return True
            if held["up"]: self.start_move(fight, "UP", held); return True
            if self.state == "dash" or self.dash_recent > 0: self.start_move(fight, "DASH", held); return True
            if self.state == "attack":
                if self.mname in ("L1", "L2"): nxt = "L%d" % (int(self.mname[1]) + 1)
                elif self.mname in ("AIR",): nxt = "AIR"
                else: nxt = "L1"
            else:
                nxt = "L%d" % (self.chain + 2) if (self.chain >= 0 and self.chain_t < 22 and self.chain < 2) else "L1"
            self.start_move(fight, nxt, held); return True
        return False

    def pick_heavy(self, fight, held):
        if not self.on_ground: cand = "AIRHEAVY"
        elif held["down"]: cand = "PILLARS"
        elif held["up"]: cand = "PHOENIX"
        elif self.state == "dash" or self.dash_recent > 0: cand = "COMET"
        else: cand = None
        if cand:
            if self.cds.get(cand, 0) <= 0: return cand
            fight.fx.text("COOLDOWN", self.x, self.y - 270, (170, 190, 220), 28, 22)
        return "FINISHER" if fight.combo >= 5 else "HEAVY"

    def cancelable(self):
        if self.state != "attack" or not self.move: return False
        c = self.move.get("cancel", 99)
        idx = self.mt * self.move["fps"] / FPS
        return idx >= c or (self.connected and idx >= c - 1 and c < 99)

    # -- main update ------------------------------------------------------------------------
    def update(self, fight, held, presses):
        self.t += 1; self.chain_t += 1
        if self.invuln > 0: self.invuln -= 1
        if self.flash > 0: self.flash -= 1
        if self.dash_cd > 0: self.dash_cd -= 1
        if self.dash_recent > 0: self.dash_recent -= 1
        if self.buf_t > 0: self.buf_t -= 1
        else: self.buf = None
        if self.pd_cd > 0: self.pd_cd -= 1
        for k in list(self.cds):
            if self.cds[k] > 0: self.cds[k] -= 1
        self.hp_trail = max(self.hp, self.hp_trail - 0.7)
        self.energy = clamp(self.energy, 0, 100)
        for p in presses:
            if not self.try_input(fight, p, held):
                self.buf = p; self.buf_t = 14
        # dead
        if self.state == "dead":
            self.dead_t += 1; self._physics(fight, 1.0); self.vx *= .9; self.x += self.vx; return
        move_x = (1 if held["right"] else 0) - (1 if held["left"] else 0)
        grav = 1.0
        if self.state in ("idle", "run"):
            self.vx = move_x * self.speed
            if move_x: self.face = move_x; self.state = "run"
            else: self.state = "idle"
            self.x += self.vx
            if self.buf and self.buf_t > 0 and self.try_input(fight, self.buf, held): pass
        elif self.state == "jump":
            self.x += move_x * self.speed * 0.95
            if move_x: self.face = move_x
            if self.buf and self.try_input(fight, self.buf, held): pass
        elif self.state == "dash":
            self.dash_t -= 1; self.x += self.vx; self.vx *= 0.93
            if self.t % 2 == 0: self.ghosts.append([self.x, self.y, self._cur_frame_info(), 14])
            if self.dash_t <= 0:
                self.state = "idle" if self.on_ground else "jump"; self.dash_recent = 12; self.vx = 0
            elif self.buf == "light": self.try_input(fight, "light", held)
        elif self.state == "attack":
            grav = self._update_attack(fight, held)
        elif self.state == "hurt":
            self.x += self.vx; self.vx *= .88; self.hurt_t -= 1
            if self.hurt_t <= 0: self.state = "idle" if self.on_ground else "jump"
        elif self.state == "down":
            self.x += self.vx; self.vx *= .9; self.down_t += 1
            if self.on_ground and self.down_t > 45: self.state = "idle"; self.invuln = max(self.invuln, 60)
        elif self.state == "ult":
            self.ult_t += 1; self.vx = 0; self.invuln = max(self.invuln, 20)
            if self.ult_t % 3 == 0:
                fight.fx.parts.append(Particle(self.x + random.uniform(-70, 70), self.y - random.uniform(0, 60), random.uniform(-.6, .6), random.uniform(-6, -3),
                                               random.randint(18, 30), (255, 190, 80) if self.char == "john" else (170, 225, 255), random.uniform(5, 10), -0.05, True))
        self._physics(fight, grav)
        self.x = clamp(self.x, 80, fight.world_w - 80)
        self.ghosts = [[g[0], g[1], g[2], g[3] - 1] for g in self.ghosts if g[3] > 1]
        if self.state not in ("attack",) and self.chain_t > 30: self.chain = -1

    def _physics(self, fight, grav):
        self.vy += GRAV * grav
        self.y += self.vy
        if self.y >= GROUND:
            was_air = not self.on_ground
            self.y = GROUND; self.on_ground = True; self.air_jumps = 1
            if was_air and self.vy > 6:
                fight.fx.dust(self.x, self.y, 8)
                if self.slam:
                    fight.slam_land(self)
            self.vy = 0
            if self.state == "jump": self.state = "idle"
            if self.state == "down" and self.down_t < 8: pass
        else:
            self.on_ground = False
            if self.state in ("idle", "run"): self.state = "jump"

    def _update_attack(self, fight, held):
        mv = self.move; fps = mv["fps"]; self.mt += 1
        idx = int(self.mt * fps / FPS)
        count = mv["frames"][1] - mv["frames"][0] + 1
        lg = mv.get("lunge")
        if lg and self.mt < lg[1]:
            self.x += self.face * lg[0] * (1 - self.mt / lg[1] * .6)
        a, b = mv["active"]
        if a <= idx <= b and mv.get("dmg", 0) > 0:
            if fight.player_hits(self, mv): self.connected = True
        if self.slam:
            self.vx = 0
        if mv.get("ghost") and self.mt % 2 == 0: self.ghosts.append([self.x, self.y, self._cur_frame_info(), 14])
        if mv.get("trail") and self.mt % 2 == 0:
            fight.fx.burst(self.x, self.y - 110, 4, (mv["trail"], (255, 255, 255)), 4, (5, 10), (12, 22), 0, True)
        pil = mv.get("pillars")
        if pil and not self.pil_done and idx >= pil["idx"]:
            self.pil_done = True; fight.spawn_pillars(self, pil)
        pr = mv.get("proj")
        if pr and not self.spawned and idx >= pr["idx"]:
            self.spawned = True; fight.spawn_player_proj(self, pr)
        nv = mv.get("nova")
        if nv and not self.novaed and idx >= nv["idx"]:
            self.novaed = True; fight.nova(self, nv)
        if mv.get("special") and a <= idx <= b and self.mt % 4 == 0:
            fight.fx.burst(self.x + self.face * 120, self.y - 120, 3, ((255, 240, 150), (255, 255, 255)), 6, (3, 7), (8, 14), 0, True)
        # buffered input in the cancel window
        if self.cancelable() and self.buf and self.buf_t > 0:
            k = self.buf
            if k in ("jump", "dash", "light", "heavy", "special"):
                self.try_input(fight, k, held)
                return 1.0
        if idx >= count and not (self.slam and not self.on_ground):
            if mv.get("endboom"): fight.blast(self, self.x + self.face * 90, mv["endboom"])
            self.move = None; self.state = "idle" if self.on_ground else "jump"; self.chain_t = 0
            self.slam = False
            if self.buf and self.buf_t > 0: self.try_input(fight, self.buf, held)
        return mv.get("floaty", 1.0) if self.vy > -8 or mv.get("floaty") else 1.0

    # -- damage -----------------------------------------------------------------------------
    def take_hit(self, fight, dmg, from_x, big=False):
        if self.invuln > 0 or self.state == "dead":
            if self.state == "dash" and self.pd_cd <= 0 and self.invuln > 0 and self.dash_t > 0: fight.perfect_dodge(self)
            return False
        self.hp -= dmg; self.flash = 8; self.energy += dmg * 0.25
        if not fight.ult: self.ult_meter = min(100.0, self.ult_meter + dmg * 0.45)
        d = 1 if self.x >= from_x else -1
        fight.combo_break()
        fight.fx.burst(self.x, self.y - 120, 10, ((255, 80, 60), (255, 200, 120)), 8)
        fight.fx.text("-%d" % dmg, self.x, self.y - 250, (255, 90, 80), 50, 45)
        fight.stop = max(fight.stop, 6); fight.fx.shake = max(fight.fx.shake, 12 if big else 8)
        fight.fx.flash = 0.25 if big else 0.1; fight.fx.flash_color = (255, 60, 40)
        audio.play("hurt", .9)
        self.move = None; self.slam = False
        if self.hp <= 0:
            self.hp = 0; self.state = "dead"; self.dead_t = 0; self.vx = d * 9; self.vy = -16; self.on_ground = False
            audio.play("ko"); fight.stop = 14; return True
        if big or not self.on_ground:
            self.state = "down"; self.down_t = 0; self.vx = d * 11; self.vy = -17; self.on_ground = False; self.invuln = 90
        else:
            self.state = "hurt"; self.hurt_t = 20; self.vx = d * 7; self.invuln = 45
        self.t = 0
        return True

    # -- drawing ----------------------------------------------------------------------------
    def _cur_frame_info(self):
        a, i = self._anim_frame()
        return (a, i, self.face < 0)

    def _anim_frame(self):
        A = self.A; st = self.state
        if st == "idle": return A["idle"], int(self.t * 10 / FPS) % A["idle"].n
        if st == "run": return A["run"], int(self.t * 20 / FPS) % A["run"].n
        if st == "dash": return A["run"], int(self.t * 30 / FPS) % A["run"].n
        if st == "jump":
            J = A["jump"]; p = clamp((self.vy + JUMP_V) / (2 * JUMP_V), 0, 1)
            return J, clamp(int(1 + p * (J.n - 2)), 0, J.n - 1)
        if st == "attack":
            mv = self.move; an = A[mv["anim"]]
            i = mv["frames"][0] + int(self.mt * mv["fps"] / FPS)
            return an, clamp(i, mv["frames"][0], min(mv["frames"][1], an.n - 1))
        if st == "ult":
            C = A["cast"]; return C, clamp(self.ult_t // 5, 0, C.n - 1)
        if st == "hurt": return A["hurt"], clamp(self.t // 4, 0, A["hurt"].n - 1)
        if st == "down":
            D = A["dead"]
            if self.down_t < 14: return D, clamp(self.down_t // 4, 0, D.n - 1)
            if self.down_t < 45 or not self.on_ground: return D, D.n - 1
            return D, clamp(D.n - 2 - (self.down_t - 45) // 5, 0, D.n - 1)
        if st == "dead":
            D = A["dead"]; return D, clamp(self.dead_t // 6, 0, D.n - 1)
        return A["idle"], 0

    def draw(self, surf, cam):
        # shadow
        hgt = clamp((GROUND - self.y) / 300, 0, 1)
        sw = int(150 * (1 - .4 * hgt)); sh = pygame.Surface((sw, 30), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, int(110 * (1 - .5 * hgt))), sh.get_rect())
        surf.blit(sh, (self.x - cam - sw / 2, GROUND - 14))
        for gx, gy, (an, i, fl), life in self.ghosts:
            an.draw(surf, i, gx, gy, cam, fl, alpha=int(110 * life / 14))
        an, i = self._anim_frame()
        blink = self.invuln > 0 and self.state not in ("attack",) and (self.invuln // 3) % 2 == 0 and self.invuln < 60 and self.state != "dash"
        if blink and self.state != "dead": return
        an.draw(surf, i, self.x, self.y, cam, self.face < 0, white=self.flash > 0)
        if self.tag and self.state != "dead":
            tx = self.x - cam; ty = self.y - 268 + math.sin(self.t * .1) * 3
            pygame.draw.polygon(surf, self.tag[1], [(tx - 16, ty), (tx + 16, ty), (tx, ty + 18)])
            text(surf, self.tag[0], font(30), self.tag[1], (tx, ty - 2), "midbottom", outline=3)

# ==============================================================================================
#  ENEMIES
# ==============================================================================================
ETYPES = {
    "acolyte": dict(name="Sith Acolyte", hp=70, scale=4.0, speed=3.2, tint=(95, 0, 0), ai="melee", dmg=10, score=100, poise=70),
    "mage": dict(name="Dark Mage", hp=45, scale=4.0, speed=2.5, tint=(0, 30, 110), ai="ranged", dmg=9, score=150, poise=45),
    "brute": dict(name="Sand Brute", hp=260, scale=5.4, speed=1.7, tint=(0, 85, 10), ai="slam", dmg=20, score=350, poise=150, armor=True),
    "leaper": dict(name="Shadow Leaper", hp=55, scale=3.8, speed=4.2, tint=(85, 0, 105), ai="leap", dmg=12, score=150, poise=50),
    "anakin": dict(name="ANAKIN", hp=1300, scale=5.0, speed=3.8, tint=None, ai="boss", dmg=14, score=3000, poise=170, armor=True),
    # ---- chapter 2 : the haunted medina (zombies)
    "walker": dict(name="Walker", hp=85, scale=4.0, speed=2.7, ai="melee", dmg=10, score=100, poise=70, fam="zombie1", death="gas"),
    "runner": dict(name="Runner", hp=55, scale=3.8, speed=4.6, ai="leap", dmg=12, score=150, poise=50, fam="zombie2", death="gas"),
    "spitter": dict(name="Spitter", hp=50, scale=4.0, speed=2.4, ai="ranged", dmg=9, score=150, poise=45, fam="zombie3", death="gas",
                    proj="gas", pspeed=9, pdmg=9, fire_i=2),
    "bloater": dict(name="Bloater", hp=300, scale=5.4, speed=1.6, ai="slam", dmg=20, score=350, poise=160, armor=True, fam="zombie4", death="gas"),
    "colossus": dict(name="PATIENT ZERO", hp=1500, scale=7.0, speed=3.0, ai="boss", dmg=15, score=3500, poise=190, armor=True, fam="zombie4",
                     tint=(0, 55, 0), death="gas", wave_proj="gas_big", extra=["eruption", "eruption"],
                     summons={2: ["walker", "walker"], 3: ["spitter", "runner", "walker"]}),
    # ---- chapter 3 : the red peaks (raiders)
    "rifleman": dict(name="Rifleman", hp=55, scale=4.0, speed=2.6, ai="ranged", dmg=9, score=150, poise=45, fam="raider1",
                     proj="bullet", pspeed=15, pdmg=8, fire_i=2, burst=2),
    "outlaw": dict(name="Outlaw", hp=60, scale=3.9, speed=4.4, ai="leap", dmg=12, score=150, poise=50, fam="raider2"),
    "thug": dict(name="Thug", hp=95, scale=4.0, speed=3.1, ai="melee", dmg=11, score=120, poise=75, fam="raider3"),
    "enforcer": dict(name="Enforcer", hp=290, scale=5.4, speed=1.8, ai="slam", dmg=20, score=380, poise=165, armor=True, fam="raider3", tint=(70, 10, 0)),
    "warlord": dict(name="WARLORD", hp=1650, scale=6.4, speed=3.6, ai="boss", dmg=15, score=3800, poise=190, armor=True, fam="raider3",
                    tint=(110, 15, 0), fire_i=2, wave_proj="bullet_big", extra=["fan", "fan", "meteor"],
                    summons={2: ["thug", "outlaw"], 3: ["rifleman", "outlaw", "thug"]}),
    # ---- chapter 4 : the scrapyard (robots)
    "drone": dict(name="Blade Drone", hp=65, scale=4.0, speed=4.0, ai="melee", dmg=11, score=130, poise=55, fam="swordsman", death="boom"),
    "trooper": dict(name="Trooper", hp=60, scale=4.0, speed=2.4, ai="ranged", dmg=9, score=150, poise=45, fam="infantry", death="boom",
                    proj="laser", pspeed=14, pdmg=9, fire_i=8),
    "crusher": dict(name="Crusher", hp=320, scale=5.4, speed=1.8, ai="slam", dmg=21, score=400, poise=170, armor=True, fam="destroyer", death="boom"),
    "megadestroyer": dict(name="MEGA DESTROYER", hp=1900, scale=7.0, speed=3.2, ai="boss", dmg=16, score=4200, poise=200, armor=True, fam="destroyer",
                          tint=(95, 0, 0), death="boom", fire_i=5, wave_proj="laser_big", extra=["meteor", "meteor", "fan"],
                          summons={2: ["trooper", "drone"], 3: ["trooper", "drone", "crusher"]}),
    # ---- chapter 5 : the summit
    "darkanakin": dict(name="DARK ANAKIN", hp=2700, scale=5.4, speed=4.2, ai="boss", dmg=17, score=6000, poise=210, armor=True, tint=(70, 0, 120),
                       wave_proj="bolt", extra=["storm", "storm", "meteor"],
                       summons={2: ["walker", "rifleman", "drone"], 3: ["acolyte", "mage", "leaper", "trooper"]}),
}


class Enemy:
    def __init__(self, kind, x, fight):
        c = ETYPES[kind]; self.kind = kind; self.cfg = c; self.scale = c["scale"]; self.A = enemy_art(c, self.scale)
        self.maxhp = int(c["hp"] * fight.hp_scale); self.hp = self.maxhp; self.boss = c["ai"] == "boss"
        self.x = float(x); self.y = float(GROUND); self.vx = 0.0; self.vy = 0.0; self.face = -1
        self.state = "spawn"; self.t = 0; self.cd = random.randint(40, 100); self.poise = 0; self.flash = 0
        self.on_ground = True; self.hit_done = False; self.token = False; self.atk = None; self.juggle = 0
        self.hurt_t = 0; self.hurt_chain = 0; self.down_t = 0; self.alpha = 255; self.step = 0
        self.hw = int(9 * self.scale); self.hh = int(52 * self.scale); self.bonus_done = False
        self.summoned = set(); self.shots = 0; self.target_x = 0; self.rec = 40; self.hp_trail = float(self.hp)
        self.fight = fight; self.name = c["name"]; self.score = c["score"]; self.sp = c["speed"]; self.combo_n = 0
        self.strafe = random.choice((-1, 1)); self.strafe_t = random.randint(30, 90)

    # -- helpers ----------------------------------------------------------------------------
    def hurtbox(self): return pygame.Rect(int(self.x - self.hw), int(self.y - self.hh), self.hw * 2, self.hh)
    def hittable(self): return self.state not in ("dead", "down", "getup")
    def k(self): return self.scale / 4.0

    def set(self, st):
        if st not in ("windup", "attack"): self.release()
        self.state = st; self.t = 0

    def release(self):
        if self.token:
            self.token = False; self.fight.tokens -= 1

    def phase(self):
        r = self.hp / self.maxhp
        return 1 if r > .66 else 2 if r > .33 else 3

    def attack_rect(self, rx, ry):
        k = self.k(); a, b = rx[0] * k, rx[1] * k
        x0 = self.x + a if self.face > 0 else self.x - b
        return pygame.Rect(int(x0), int(self.y + ry[0] * k), int(b - a), int((ry[1] - ry[0]) * k))

    # -- taking damage ----------------------------------------------------------------------
    def take_hit(self, fight, dmg, kbx, kby, stun, launch, juggle):
        if not self.hittable(): return None
        self.hp -= dmg; self.flash = 6
        if self.hp <= 0:
            self.die(fight, kbx); return "kill"
        self.release()
        if self.state == "air":
            self.vx = kbx * .6
            if juggle and self.juggle < 6: self.vy = min(self.vy, -9); self.juggle += 1
            elif kby < 0: self.vy = kby * .8
            return "hit"
        if self.cfg.get("armor"):
            self.poise += dmg * (1.5 if launch else 1)
            self.x += kbx * .12
            if self.poise >= self.cfg["poise"]:
                self.poise = 0; self.state = "air"; self.t = 0; self.vx = kbx * .7; self.vy = -13; self.on_ground = False
                fight.fx.text("STAGGER!", self.x, self.y - self.hh - 30, GOLD, 46, 40)
            elif self.state in ("windup",):
                pass
            return "hit"
        self.hurt_chain += 1
        if launch or not self.on_ground or self.hurt_chain >= 5:
            self.state = "air"; self.t = 0; self.vx = kbx; self.vy = kby if kby < 0 else -13; self.on_ground = False; self.hurt_chain = 0
        else:
            self.state = "hurt"; self.t = 0; self.hurt_t = stun; self.vx = kbx * .9
        return "hit"

    def die(self, fight, kbx):
        self.release(); self.state = "dead"; self.t = 0; self.vx = kbx * .8; self.vy = -14; self.on_ground = False
        self.hp = 0; fight.on_kill(self)

    # -- update -----------------------------------------------------------------------------
    def update(self, fight):
        self.fight = fight; self.t += 1
        if self.flash > 0: self.flash -= 1
        self.hp_trail = max(self.hp, self.hp_trail - 1.2)
        p = fight.target_player(self.x); st = self.state
        if self.cd > 0: self.cd -= 1
        # physics
        if not self.on_ground:
            self.vy += GRAV * (0.55 if st == "air" and self.vy < 0 and self.juggle else 1.0)
            self.y += self.vy; self.x += self.vx; self.vx *= .985
            if self.y >= GROUND: self.land(fight)
        else:
            self.x += self.vx; self.vx *= .82
        self.x = clamp(self.x, 60, fight.world_w - 60)
        dx = p.x - self.x; dist = abs(dx)

        if st == "spawn":
            self.face = 1 if dx > 0 else -1; self.x += self.face * self.sp * 2.2
            if self.t > 36 or (fight.cam - 20 < self.x < fight.cam + W + 20 and self.t > 14):
                self.set("chase")
        elif st == "chase":
            self.chase(fight, p, dx, dist)
        elif st == "windup":
            self.vx = 0
            if self.t == 1 and not self.boss: fight.fx.text("!", self.x, self.y - self.hh - 20, (255, 70, 60), 60, 26, -.5)
            if self.t >= self.windup_len(): self.set("attack"); self.hit_done = False; self.begin_attack(fight, p)
        elif st == "attack":
            self.update_attack(fight, p, dx)
        elif st == "recover":
            self.vx *= .8
            if self.t >= self.rec: self.set("chase")
        elif st == "hurt":
            self.hurt_t -= 1
            if self.hurt_t <= 0: self.hurt_chain = max(0, self.hurt_chain - 1); self.set("chase")
        elif st == "down":
            self.vx *= .8
            if self.t > 55: self.set("getup")
        elif st == "getup":
            if self.t > 16: self.set("chase"); self.cd = max(self.cd, 20); self.hurt_chain = 0
        elif st == "dead":
            if self.on_ground: self.vx *= .85
            if self.t > 70 and not self.boss: self.alpha = max(0, 255 - (self.t - 70) * 9)
        # separation so they don't stack
        if st in ("chase", "recover", "windup"):
            for o in fight.enemies:
                if o is not self and o.state in ("chase", "recover", "windup") and abs(o.x - self.x) < 90:
                    self.x += (1 if self.x >= o.x else -1) * 1.6

    def land(self, fight):
        self.y = GROUND; self.vy = 0; self.on_ground = True
        fight.fx.dust(self.x, self.y, 7)
        if self.state == "air":
            self.state = "down" if self.hp > 0 else "dead"; self.t = 0; self.juggle = 0; self.vx *= .3
            fight.fx.shake = max(fight.fx.shake, 4)
        elif self.state == "dead":
            self.vx *= .3
        elif self.state == "attack" and self.atk in ("leap", "bleap"):
            self.vx = 0
            if self.atk == "bleap":
                fight.aoe_on_player(self, 340, self.cfg["dmg"] + 8, big=True, cy=(-120, 40))
                fight.fx.ring(self.x, self.y - 10, 360, (255, 150, 60), 30, 14); fight.fx.shake = 22; audio.play("slam")
                fight.fx.burst(self.x, self.y - 20, 22, ((255, 190, 110), (255, 255, 255)), 12)
            self.set("recover"); self.rec = 40 if self.atk == "leap" else 48 - 6 * (self.phase() - 1)

    # -- AI ---------------------------------------------------------------------------------
    def windup_len(self):
        return {"melee": 24, "shoot": 34, "slam": 38, "leap": 18, "wave": 30, "dash": 22, "combo": 22, "bleap": 34, "shock": 34, "summon": 30,
                "storm": 44, "meteor": 40, "eruption": 36, "fan": 28}.get(self.atk, 24)

    def hit_win(self):
        n = self.A["a2"].n; lo = max(1, int(round(n * .45))); return lo, lo + 2

    def move_to(self, tx, spd):
        d = tx - self.x
        if abs(d) > spd: self.x += spd * (1 if d > 0 else -1)
        return abs(d)

    def chase(self, fight, p, dx, dist):
        self.face = 1 if dx > 0 else -1
        ai = self.cfg["ai"]; k = self.k(); sp = self.sp * (1.25 if self.boss and self.phase() == 3 else 1)
        self.step += 1
        if p.state == "dead": return
        can_attack = self.cd <= 0 and (self.token or fight.tokens < fight.max_tokens or self.boss)
        if ai == "melee":
            rng = 185 * k
            if dist > rng * .85: self.x += self.face * sp
            elif dist < rng * .45: self.x -= self.face * sp * .6
            if dist < rng * 1.1 and can_attack: self.start_attack(fight, "melee")
            elif self.cd > 0 or not can_attack: self.circle(sp, dist, 330)
        elif ai == "ranged":
            if dist < 430: self.x -= self.face * sp * 1.1
            elif dist > 800: self.x += self.face * sp
            else: self.circle(sp, dist, 0, True)
            if can_attack and 380 < dist < 1000 and fight.on_screen(self.x): self.start_attack(fight, "shoot")
        elif ai == "slam":
            rng = 230 * k
            if dist > rng * .8: self.x += self.face * sp
            if dist < rng and can_attack: self.start_attack(fight, "slam")
        elif ai == "leap":
            if dist > 520: self.x += self.face * sp
            elif dist < 260: self.x -= self.face * sp * .8
            else: self.circle(sp, dist, 0, True)
            if can_attack and 300 < dist < 700: self.start_attack(fight, "leap")
        elif ai == "boss":
            if self.cd <= 0: self.boss_pick(fight, p, dist)
            else:
                if dist > 264 * k: self.x += self.face * sp
                elif dist < 144 * k: self.x -= self.face * sp * .5

    def circle(self, sp, dist, keep, always=False):
        self.strafe_t -= 1
        if self.strafe_t <= 0: self.strafe = random.choice((-1, 1)); self.strafe_t = random.randint(40, 100)
        if always or dist < keep: self.x += self.strafe * sp * .45

    def start_attack(self, fight, atk):
        if not self.boss:
            if not self.token:
                self.token = True; fight.tokens += 1
        self.atk = atk; self.set("windup"); self.hit_done = False; self.shots = 0
        if atk in ("storm", "meteor", "eruption"): fight.boss_hazards(self, atk)

    def boss_pick(self, fight, p, dist):
        ph = self.phase(); opts = []
        if ph >= 2 and ph not in self.summoned and len(fight.enemies) < 4:
            self.summoned.add(ph); self.start_attack(fight, "summon"); return
        if dist > 650: opts = ["wave", "wave", "dash", "bleap"]
        elif dist > 300: opts = ["dash", "wave", "bleap", "combo"]
        else: opts = ["combo", "combo", "shock", "bleap"]
        opts = opts + list(self.cfg.get("extra", [])) * (1 if ph == 1 else 2)
        last = getattr(self, "last_atk", None)
        if last in opts and len(set(opts)) > 1: opts = [o for o in opts if o != last] or opts
        self.last_atk = random.choice(opts)
        self.start_attack(fight, self.last_atk)
        if self.atk == "bleap":
            fight.fx.text("LOOK OUT!", self.x, self.y - self.hh - 30, (255, 90, 60), 48, 40)

    def begin_attack(self, fight, p):
        self.face = 1 if p.x >= self.x else -1; a = self.atk
        if a in ("leap", "bleap"):
            self.vy = -22 if a == "leap" else -31; self.on_ground = False
            T = 2 * abs(self.vy) / GRAV
            self.vx = clamp((p.x - self.x) / T, -15, 15) if a == "bleap" else self.face * clamp(abs(p.x - self.x) / T * 1.1, 6, 15)
            audio.play("jump", .8)
        elif a == "dash":
            self.vx = self.face * 15; audio.play("dash", .8)
        elif a == "summon":
            fight.summon(self)
        elif a in ("shoot", "wave") or a in ("melee", "combo", "slam", "shock"):
            pass

    def update_attack(self, fight, p, dx):
        a = self.atk; t = self.t; k = self.k()
        if a == "melee":
            i = int(t * 15 / FPS); lo, hi = self.hit_win()
            if lo <= i <= hi and not self.hit_done: self.try_hit_player(fight, p, (0, 205), (-235, -20), self.cfg["dmg"], 7)
            if i >= self.A["a2"].n: self.set("recover"); self.rec = random.randint(40, 65); self.cd = random.randint(40, 110)
        elif a == "shoot":
            i = int(t * 17 / FPS); c = self.cfg; n = self.A["atk"].n; fi = c.get("fire_i", 4); ei = c.get("end_i", max(fi + 2, n - 4))
            while self.shots < c.get("burst", 1) and i >= fi + self.shots * 2:
                self.shots += 1; fight.spawn_enemy_proj(self, c.get("proj", "blue"), c.get("pspeed", 11), c.get("pdmg", 9), 120 * k)
            if i >= ei + (c.get("burst", 1) - 1) * 2: self.set("recover"); self.rec = random.randint(50, 80); self.cd = random.randint(110, 190)
        elif a in ("slam", "shock"):
            i = int(t * 9 / FPS)
            if i >= min(3, self.A["a1"].n - 1) and not self.hit_done:
                self.hit_done = True; rad = 260 * k if a == "slam" else 340
                fight.aoe_on_player(self, rad, self.cfg["dmg"], big=True, cy=(-140, 40))
                fight.fx.ring(self.x + self.face * 80, self.y - 8, rad, (255, 190, 90), 28, 14); fight.fx.shake = max(fight.fx.shake, 16)
                fight.fx.burst(self.x + self.face * 100, self.y - 20, 16, ((255, 200, 120), (255, 255, 255)), 10); audio.play("slam")
            if i >= self.A["a1"].n: self.set("recover"); self.rec = random.randint(55, 80) if not self.boss else 36; self.cd = random.randint(60, 120) if not self.boss else 24
        elif a == "leap":
            if self.vy > 0 and not self.hit_done: self.try_hit_player(fight, p, (-40, 190), (-230, 0), self.cfg["dmg"], 9)
        elif a == "bleap":
            if t > 4 and not self.on_ground:
                self.x += 0
        elif a == "wave":
            i = int(t * 15 / FPS); ph = self.phase()
            shots = [5] if ph == 1 else [5, 10] if ph == 2 else [5, 8, 11]
            nA = self.A["atk"].n; shots = [min(q, nA - 3) for q in shots]
            if self.shots < len(shots) and i >= shots[self.shots]:
                fight.spawn_enemy_proj(self, self.cfg.get("wave_proj", "blue_big"), 10.5 + ph, 14, 90 * k, ground_y=-(70 + (190 if (ph > 1 and self.shots == 1) else 0)))
                self.shots += 1; audio.play("wave", .8)
            if i >= self.A["atk"].n - 2: self.set("recover"); self.rec = 40 - 6 * (ph - 1); self.cd = 22
        elif a == "dash":
            self.x += self.vx; self.face = 1 if p.x >= self.x else -1
            if t % 3 == 0: fight.fx.dust(self.x, self.y, 2, -self.face)
            if abs(p.x - self.x) < 200 * k or t > 40:
                self.atk = "combo"; self.t = 0; self.shots = 0; self.vx = 0
        elif a == "combo":
            i = int(t * 15 / FPS)
            hits = 2 if self.phase() == 1 else 3; lo, hi = self.hit_win()
            if lo <= i <= hi and self.shots < hits and t > 0 and not self.hit_done:
                self.try_hit_player(fight, p, (0, 235), (-250, -20), self.cfg["dmg"], 8, big=(self.shots == hits - 1))
            if i >= self.A["a2"].n:
                self.shots += 1; self.hit_done = False; self.t = 0
                self.face = 1 if p.x >= self.x else -1; self.x += self.face * 70
                if self.shots >= hits: self.set("recover"); self.rec = 38 - 6 * (self.phase() - 1); self.cd = 16
        elif a == "fan":
            i = int(t * 15 / FPS); ph = self.phase(); fi = self.cfg.get("fire_i", 2); nA = self.A["atk"].n
            if self.shots < 1 and i >= fi:
                self.shots = 1; cnt = 3 + 2 * (ph - 1); audio.play("wave", .8)
                for j in range(cnt):
                    fight.spawn_enemy_proj(self, self.cfg.get("wave_proj", "blue_big"), 9.5 + ph, 11, 90 * k, ground_y=-110, vy=(j - (cnt - 1) / 2) * 1.7)
            if i >= max(fi + 3, nA - 2): self.set("recover"); self.rec = 40 - 6 * (ph - 1); self.cd = 24
        elif a in ("summon", "storm", "meteor", "eruption"):
            i = int(t * 9 / FPS)
            if i >= self.A["a1"].n: self.set("recover"); self.rec = 36; self.cd = 40 if a == "summon" else 26

    def try_hit_player(self, fight, p, rx, ry, dmg, kb, big=False):
        r = self.attack_rect(rx, ry)
        if r.colliderect(p.hurtbox()):
            if p.take_hit(fight, dmg, self.x, big):
                self.hit_done = True
                if kb: p.vx += (1 if p.x >= self.x else -1) * 2

    # -- drawing ----------------------------------------------------------------------------
    def anim_frame(self):
        A = self.A; st = self.state; t = self.t
        if st == "spawn": return A["run"], int(self.step * .25 + t * .3) % A["run"].n
        if st == "chase":
            if self.boss or self.kind in ("acolyte", "leaper"):
                return A["run"], int(self.step * .22) % A["run"].n
            return A["walk"], int(self.step * .18) % A["walk"].n
        if st == "windup":
            a = self.atk
            if a == "shoot": return A["arrow"], clamp(t // 5, 0, A["arrow"].n - 1)
            if a in ("slam", "shock", "summon", "storm", "meteor", "eruption"): return A["a1"], clamp(t // 12, 0, min(2, A["a1"].n - 1))
            if a in ("leap", "bleap"): return A["jump"], clamp(t // 6, 0, 1)
            if a in ("wave", "fan"): return A["atk"], clamp(t // 12, 0, 2)
            return A["a2"], clamp(t // 12, 0, 1)
        if st == "attack":
            a = self.atk
            if a in ("melee", "combo"): return A["a2"], clamp(int(t * 15 / FPS), 0, A["a2"].n - 1)
            if a == "shoot": return A["atk"], clamp(int(t * 17 / FPS), 0, A["atk"].n - 1)
            if a in ("wave", "fan"): return A["atk"], clamp(int(t * 15 / FPS), 0, A["atk"].n - 1)
            if a in ("slam", "shock", "summon", "storm", "meteor", "eruption"): return A["a1"], clamp(int(t * 9 / FPS), 0, A["a1"].n - 1)
            if a == "dash": return A["run"], int(t * .5) % A["run"].n
            if a in ("leap", "bleap"):
                J = A["jump"]; p = clamp((self.vy + 31) / 62, 0, 1); return J, clamp(int(1 + p * (J.n - 2)), 0, J.n - 1)
        if st == "recover": return A["idle"], int(t * .15) % A["idle"].n
        if st == "hurt": return A["hurt"], clamp(t // 4, 0, A["hurt"].n - 1)
        if st == "air":
            D = A["dead"]; return D, clamp(t // 5, 0, 2)
        if st == "down": return A["dead"], A["dead"].n - 1
        if st == "getup":
            D = A["dead"]; return D, clamp(D.n - 1 - t // 6, 0, D.n - 1)
        if st == "dead":
            D = A["dead"]; return D, clamp(t // 6, 0, D.n - 1)
        return A["idle"], int(t * .15) % A["idle"].n

    def draw(self, surf, cam, tick):
        hgt = clamp((GROUND - self.y) / 300, 0, 1)
        sw = int(self.hw * 2.6 * (1 - .4 * hgt)); sh = pygame.Surface((sw, 28), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, int(100 * (1 - .5 * hgt) * self.alpha / 255)), sh.get_rect())
        surf.blit(sh, (self.x - cam - sw / 2, GROUND - 13))
        an, i = self.anim_frame()
        white = self.flash > 0 or (self.state == "windup" and (self.t // 3) % 2 == 0 and self.t > 4)
        an.draw(surf, i, self.x, self.y, cam, self.face < 0, white=white, alpha=self.alpha)
        if self.boss and self.phase() == 3 and tick % 4 == 0 and self.state != "dead":
            self.fight.fx.parts.append(Particle(self.x + random.uniform(-50, 50), self.y - random.uniform(0, 250), random.uniform(-.5, .5), -2.5, 28,
                                                (255, 60, 40), 7, -0.05, True))
        if self.atk == "bleap" and self.state == "windup":     # landing marker
            m = pygame.Surface((340, 60), pygame.SRCALPHA); pygame.draw.ellipse(m, (255, 40, 40, 90 + int(70 * math.sin(self.t * .5))), m.get_rect(), 6)
            pygame.draw.ellipse(m, (255, 40, 40, 50), m.get_rect().inflate(-70, -14))
            surf.blit(m, (self.fight.player.x - cam - 170, GROUND - 28))
        # little hp bar for non-boss
        if not self.boss and self.state not in ("dead",) and self.hp < self.maxhp:
            bw = int(self.hw * 2.2); bx = self.x - cam - bw / 2; by = self.y - self.hh - 26
            pygame.draw.rect(surf, (20, 0, 0), (bx - 2, by - 2, bw + 4, 12), border_radius=4)
            pygame.draw.rect(surf, (200, 200, 200), (bx, by, bw * self.hp_trail / self.maxhp, 8), border_radius=3)
            pygame.draw.rect(surf, (230, 50, 50), (bx, by, bw * self.hp / self.maxhp, 8), border_radius=3)


# ==============================================================================================
#  PROJECTILES & PICKUPS
# ==============================================================================================
class Projectile:
    PROJ_R = {"gas": 34, "gas_big": 62, "bullet": 20, "bullet_big": 32, "laser": 24, "laser_big": 40, "bolt": 44,
              "fire": 44, "fire_big": 66, "light": 61, "light_big": 90, "blue": 49, "blue_big": 71}

    def __init__(self, x, y, vx, dmg, kind, friendly, kb=(8, -4), stun=18, pierce=False, launch=False, life=110, big=False, vy=0.0, aoe=0):
        self.vy = vy; self.aoe = aoe
        self.x = x; self.y = y; self.vx = vx; self.dmg = dmg; self.friendly = friendly; self.kb = kb; self.stun = stun
        self.pierce = pierce; self.launch = launch; self.life = life; self.t = 0; self.kind = kind
        self.fly, self.hit = fx_art()[kind]; self.dead = False; self.hit_ids = set()
        self.r = Projectile.PROJ_R.get(kind) or int(34 * self.fly.scale / 3.6) + 10

    def rect(self): return pygame.Rect(int(self.x - self.r), int(self.y - self.r * .8), self.r * 2, int(self.r * 1.6))

    def update(self, fight):
        self.t += 1; self.x += self.vx; self.y += self.vy; self.life -= 1
        if self.life <= 0 or self.x < -300 or self.x > fight.world_w + 300:
            self.dead = True; return
        if self.vy > 0 and self.y >= GROUND - 70:
            self.explode(fight); return
        fam = self.kind.split("_")[0]; bigk = self.kind.endswith("big"); pf = fight.fx.parts
        if fam == "fire":                                   # flying embers
            for _ in range(4 if bigk else 2):
                pf.append(Particle(self.x - abs(self.vx) * random.uniform(0, 2.5) * (1 if self.vx > 0 else -1) + random.uniform(-8, 8),
                                   self.y + random.uniform(-20, 20) * (2 if bigk else 1), -self.vx * random.uniform(.05, .18), random.uniform(-2.4, -.4),
                                   random.randint(16, 30), random.choice(((255, 210, 80), (255, 140, 30), (230, 70, 20))),
                                   random.uniform(4, 11 if bigk else 8), -0.04, True))
        elif fam in ("light", "blue"):                      # electric sparks
            if self.t % 2 == 0:
                for _ in range(4 if bigk else 2):
                    pf.append(Particle(self.x + random.uniform(-14, 14), self.y + random.uniform(-26, 26), random.uniform(-3, 3), random.uniform(-3, 3),
                                       random.randint(8, 16), random.choice(((210, 230, 255), (255, 255, 255), (255, 240, 170))),
                                       random.uniform(2, 5), 0, True))
        elif self.t % 2 == 0:
            col = {"gas": (110, 240, 110), "bullet": (255, 200, 80), "laser": (110, 220, 255), "bolt": (190, 150, 255)}[fam]
            pf.append(Particle(self.x, self.y + random.uniform(-14, 14), -self.vx * .1, random.uniform(-1, 1), 14, col, 6, 0, True))
        r = self.rect()
        if self.friendly:
            for e in fight.enemies:
                if e.hittable() and id(e) not in self.hit_ids and r.colliderect(e.hurtbox()):
                    self.hit_ids.add(id(e)); fight.hit_enemy_proj(self, e)
                    if not self.pierce: self.explode(fight); return
            ow = getattr(self, "owner", None)
            if fight.vs and ow is not None:                      # versus: projectiles hurt the other player
                t = fight.rival(ow)
                if t.state != "dead" and id(t) not in self.hit_ids and r.colliderect(t.hurtbox()):
                    self.hit_ids.add(id(t))
                    fight.vs_hit(ow, t, self.dmg, self.x - (1 if self.vx > 0 else -1) * 50, big=bool(self.launch) or self.kind.endswith("big"))
                    if not self.pierce: self.explode(fight); return
        else:
            for p in fight.players:
                if r.colliderect(p.hurtbox()) and p.state != "dead":
                    if p.take_hit(fight, self.dmg, self.x - (1 if self.vx > 0 else -1) * 50, big=self.kind.endswith("big")):
                        self.explode(fight); return

    def explode(self, fight):
        self.dead = True
        fight.fx.sprite(self.hit, self.x, self.y, 18, self.vx < 0)
        fight.fx.burst(self.x, self.y, 10, ((255, 200, 100), (255, 255, 255)), 8)
        fam = self.kind.split("_")[0]; bigk = self.kind.endswith("big"); fx = fight.fx
        if self.friendly and fam in ("fire", "light", "blue"):
            if fam == "fire":
                fx.ring(self.x, min(self.y, GROUND - 40), 210 if bigk else 130, (255, 170, 60), 20, 10, .6)
                fx.burst(self.x, self.y, 22 if bigk else 12, ((255, 230, 120), (255, 140, 40), (255, 255, 255)), 12 if bigk else 9, (3, 9), (14, 28), .25)
                if self.y > GROUND - 300: fx.boom("fire", self.x, GROUND + 12, 3.6 if bigk else 2.4, 15, "bottom", 128)
            else:
                fx.ring(self.x, min(self.y, GROUND - 40), 210 if bigk else 130, (170, 215, 255), 20, 10, .6)
                fx.burst(self.x, self.y, 22 if bigk else 12, ((200, 230, 255), (255, 255, 255), (150, 190, 255)), 12 if bigk else 9, (2, 6), (12, 24), 0)
                fx.boom("lightning", self.x, GROUND + 14, 3.8 if bigk else 2.5, 26, "bottom", 64)
                fx.flash = max(fx.flash, .12 if bigk else .05); fx.flash_color = (200, 225, 255)
            fx.shake = max(fx.shake, 8 if bigk else 3)
        if self.aoe and self.friendly:
            fire = self.kind.startswith("fire")
            fight.fx.boom("boom_ground" if fire else "blue_circle", self.x, min(self.y, GROUND - 80), 2.0, 22)
            fight.fx.ring(self.x, GROUND - 10, self.aoe * 1.4, (255, 170, 60) if fire else (170, 225, 255), 22, 12)
            fight.fx.shake = max(fight.fx.shake, 12); fight.fx.zoom_kick = max(fight.fx.zoom_kick, .03); audio.play("boom", .7)
            for e in fight.enemies:
                if e.hittable() and id(e) not in self.hit_ids and abs(e.x - self.x) < self.aoe + e.hw:
                    self.hit_ids.add(id(e)); fight.hit_enemy_proj(self, e)

    def draw(self, surf, cam):
        self.fly.draw(surf, int(self.t * (self.fly.fps if isinstance(self.fly, GlowAnim) else 16) / FPS) % self.fly.n, self.x, self.y, cam, self.vx < 0)


class Pickup:
    IMG = None
    def __init__(self, x, y=GROUND - 45):
        if Pickup.IMG is None:
            Pickup.IMG = pygame.transform.smoothscale(img("felfel.png"), (91, 92))
        self.x = x; self.y = y; self.t = random.randint(0, 100); self.dead = False; self.vy = -12; self.base = GROUND - 50

    def update(self, fight):
        self.t += 1
        if self.vy or self.y < self.base:
            self.vy += .8; self.y += self.vy
            if self.y >= self.base: self.y = self.base; self.vy = 0
        for p in fight.players:
            if p.state != "dead" and p.hurtbox().inflate(40, 40).collidepoint(self.x, self.y):
                heal = int(p.maxhp * .30); p.hp = min(p.maxhp, p.hp + heal); self.dead = True
                fight.fx.text("+%d HP" % heal, p.x, p.y - 260, GREEN, 52, 55); audio.play("pickup")
                fight.fx.burst(self.x, self.y, 14, ((90, 255, 120), (255, 255, 255)), 7)
                break

    def draw(self, surf, cam):
        by = self.y + math.sin(self.t * .1) * 8
        g = pygame.Surface((150, 150), pygame.SRCALPHA); pygame.draw.circle(g, (120, 255, 120, 60 + int(30 * math.sin(self.t * .15))), (75, 75), 68)
        surf.blit(g, (self.x - cam - 75, by - 75)); surf.blit(Pickup.IMG, (self.x - cam - 45, by - 46))

# ==============================================================================================
#  SCENE BASE
# ==============================================================================================
class Scene:
    def __init__(self, game): self.game = game
    def enter(self): pass
    def event(self, e): pass
    def update(self): pass
    def draw(self, surf): pass


_bg_cache = {}
def bg_cover(name):
    if name not in _bg_cache:
        _bg_cache[name] = cover(img(name))
    return _bg_cache[name]


def bar(surf, rect, frac, color, back=(25, 25, 30), trail=None, border=(0, 0, 0), r=8):
    x, y, w, h = rect
    rrect(surf, border, (x - 3, y - 3, w + 6, h + 6), r + 2)
    rrect(surf, back, rect, r)
    if trail is not None and trail > frac:
        rrect(surf, (235, 235, 235), (x, y, max(0, w * trail), h), r)
    if frac > 0:
        rrect(surf, color, (x, y, max(r, w * frac), h), r)
        shine = pygame.Surface((int(max(r, w * frac)), h // 3), pygame.SRCALPHA); shine.fill((255, 255, 255, 45))
        surf.blit(shine, (x, y + 2))


# ==============================================================================================
#  HAZARDS  (delayed ground strikes: player pillars / ultimate strikes / boss storms)
# ==============================================================================================
class Hazard:
    COL = {"bolt": (190, 140, 255), "meteor": (255, 100, 40), "toxic": (110, 255, 110), "fire": (255, 170, 60)}

    def __init__(self, fight, x, delay, kind, friendly, dmg, r=120, owner=None, mv=None):
        self.x = float(x); self.delay = delay; self.kind = kind; self.friendly = friendly; self.dmg = dmg; self.r = r
        self.owner = owner; self.mv = mv; self.t = 0; self.fired = False; self.dead = False; self.life = 14
        self.src = (self.x + random.choice((-1, 1)) * random.uniform(380, 640), -240.0)

    def update(self, fight):
        self.t += 1
        if not self.fired and self.t >= self.delay: self.fire(fight)
        if self.fired:
            self.life -= 1
            if self.life <= 0: self.dead = True

    def fire(self, fight):
        self.fired = True; fx = fight.fx; k = self.kind; x = self.x
        if k == "fire":
            fx.boom("fire", x, GROUND + 14, 6.0, 15, "bottom", 128); fx.boom("boom_ground", x, GROUND - 60, 2.4, 20)
            fx.ring(x, GROUND - 8, self.r * 1.8, (255, 170, 60), 20, 12); fx.shake = max(fx.shake, 9)
            fx.burst(x, GROUND - 60, 14, ((255, 200, 90), (255, 120, 30), (255, 255, 255)), 11)
        elif k == "bolt":
            fx.boom("lightning", x, GROUND + 14, 6.2, 26, "bottom", 64); fx.boom("impact", x, GROUND - 70, 2.2, 22)
            fx.ring(x, GROUND - 8, self.r * 1.8, (170, 225, 255), 20, 12); fx.shake = max(fx.shake, 10)
            fx.flash = max(fx.flash, .14); fx.flash_color = (200, 230, 255)
            fx.burst(x, GROUND - 60, 14, ((190, 230, 255), (255, 255, 255), (150, 150, 255)), 12)
        elif k == "meteor":
            fx.boom("boom_big", x, GROUND - 120, 2.0, 18); fx.boom("boom_ground", x, GROUND - 70, 1.7, 22)
            fx.ring(x, GROUND - 8, self.r * 1.7, (255, 150, 60), 22, 12); fx.shake = max(fx.shake, 13)
            fx.burst(x, GROUND - 60, 16, ((255, 200, 90), (255, 110, 30), (255, 255, 255)), 12)
        else:
            fx.boom("gas", x, GROUND - 100, 2.1, 16); fx.ring(x, GROUND - 8, self.r * 1.6, (120, 255, 120), 20, 10)
            fx.shake = max(fx.shake, 8); fx.burst(x, GROUND - 60, 14, ((120, 255, 120), (210, 255, 200)), 9)
        audio.play("boom" if k in ("meteor", "fire") else "slam", .7)
        if self.friendly:
            for e in list(fight.enemies):
                if e.hittable() and abs(e.x - x) < self.r + e.hw and e.y > GROUND - 650:
                    fight.hit_enemy(self.owner, e, self.mv)
            if fight.vs and self.owner is not None: fight.vs_aoe(self.owner, x, self.r, self.mv["dmg"])
        else:
            for p in fight.players:
                if abs(p.x - x) < self.r + 30 and p.y > GROUND - 280 and p.state != "dead":
                    p.take_hit(fight, self.dmg, x, big=True)

    def draw(self, surf, cam):
        if self.fired: return
        x = self.x - cam; prog = clamp(self.t / max(1, self.delay), 0, 1); col = Hazard.COL.get(self.kind, WHITE)
        if self.friendly and self.kind in ("fire", "bolt"):
            g = pygame.Surface((int(self.r * 2), 40), pygame.SRCALPHA)
            pygame.draw.ellipse(g, (*col, int(110 * prog)), g.get_rect()); surf.blit(g, (x - self.r, GROUND - 22)); return
        w = int(self.r * 2)
        m = pygame.Surface((w + 12, 64), pygame.SRCALPHA)
        pulse = 90 + int(70 * math.sin(self.t * .5))
        pygame.draw.ellipse(m, (*col, pulse), (6, 4, w, 56), 6)
        iw = max(4, int(w * prog)); ih = max(4, int(56 * prog))
        pygame.draw.ellipse(m, (*col, 70), (6 + (w - iw) // 2, 4 + (56 - ih) // 2, iw, ih))
        surf.blit(m, (x - self.r - 6, GROUND - 30))
        if self.kind == "meteor" or (self.friendly and self.kind == "meteor"):
            e = prog ** 1.5; sx, sy = self.src; tx, ty = self.x, GROUND - 110
            for j in range(9, -1, -1):
                q = clamp(e - j * 0.028, 0, 1); px = lerp(sx, tx, q) - cam; py = lerp(sy, ty, q)
                rad = max(3, int((26 - j * 2.2) * (0.5 + .5 * prog)))
                c = (255, int(230 - j * 14), int(120 - j * 10))
                pygame.draw.circle(surf, c, (int(px), int(py)), rad)
        elif self.kind == "bolt" and prog > .55:
            a = pygame.Surface((14, GROUND), pygame.SRCALPHA); a.fill((220, 200, 255, int(90 * (prog - .5) * 2)))
            surf.blit(a, (x - 7, 0))


# ==============================================================================================
#  CHAPTERS
# ==============================================================================================
def _w(title, sub, spawn, boss=False): return dict(title=title, sub=sub, spawn=spawn, boss=boss)

CHAPTERS = [
    dict(num=1, key="tataouine", name="TATAOUINE", sub="Sand and Sith", music="bg_music.mp3", amb="sand", decor="desert",
         vig=(25, 8, 0), grade=None, boss="anakin",
         waves=[_w("WAVE 1", "Warm up, habibi!", ["acolyte", "acolyte", "acolyte"]),
                _w("WAVE 2", "They brought a mage", ["acolyte", "acolyte", "mage", "acolyte", "mage"]),
                _w("WAVE 3", "Watch the leapers!", ["leaper", "acolyte", "leaper", "mage", "acolyte", "leaper"]),
                _w("WAVE 4", "Sand Brutes incoming", ["brute", "acolyte", "mage", "acolyte", "leaper", "brute"]),
                _w("BOSS FIGHT", "ANAKIN", ["anakin"], True)]),
    dict(num=2, key="medina", name="THE HAUNTED MEDINA", sub="Something moves in the dark...", music="bg_music.mp3", amb="ash", decor="cave",
         bg_file="ch2_ghost.png", floor=(10, 0, 20), vig=(15, 0, 30), grade=(40, 0, 70, 38), boss="colossus",
         waves=[_w("WAVE 1", "They are not sleeping...", ["walker", "walker", "walker", "walker"]),
                _w("WAVE 2", "Fast ones! Keep moving", ["walker", "runner", "walker", "spitter", "runner"]),
                _w("WAVE 3", "Bloaters in the fog", ["bloater", "walker", "spitter", "runner", "walker", "bloater"]),
                _w("BOSS FIGHT", "PATIENT ZERO", ["colossus"], True)]),
    dict(num=3, key="peaks", name="JEBEL CHAMBI", sub="The raiders of the red peaks", music="bg_music.mp3", amb="ember", decor="canyon",
         bg_file="ch3_peaks.png", floor=(40, 5, 15), vig=(40, 0, 10), grade=(255, 90, 60, 22), boss="warlord",
         waves=[_w("WAVE 1", "Raiders on the ridge", ["thug", "thug", "rifleman", "thug"]),
                _w("WAVE 2", "Take cover!", ["rifleman", "outlaw", "thug", "rifleman", "outlaw"]),
                _w("WAVE 3", "The Enforcers arrive", ["enforcer", "rifleman", "outlaw", "thug", "outlaw", "enforcer"]),
                _w("BOSS FIGHT", "THE WARLORD", ["warlord"], True)]),
    dict(num=4, key="scrapyard", name="THE SCRAPYARD", sub="Machines never sleep", music="bg_music.mp3", amb="spark", decor="middle_lane",
         bg_file="ch4_factory.png", floor=(15, 15, 25), vig=(0, 10, 25), grade=(40, 120, 255, 26), boss="megadestroyer",
         waves=[_w("WAVE 1", "Blade drones online", ["drone", "drone", "drone", "drone"]),
                _w("WAVE 2", "Targeting you...", ["trooper", "drone", "trooper", "drone", "trooper"]),
                _w("WAVE 3", "Crushers deployed", ["crusher", "trooper", "drone", "drone", "trooper", "crusher"]),
                _w("BOSS FIGHT", "MEGA DESTROYER", ["megadestroyer"], True)]),
    dict(num=5, key="summit", name="THE SUMMIT", sub="Everyone you beat is back", music="bg_music.mp3", amb="snow", decor="snowy",
         bg_file="ch5_summit.png", floor=(20, 15, 35), vig=(10, 5, 30), grade=(120, 60, 255, 30), boss="darkanakin",
         waves=[_w("WAVE 1", "The old enemies return", ["acolyte", "walker", "thug", "drone", "mage"]),
                _w("WAVE 2", "A little of everything", ["mage", "rifleman", "trooper", "runner", "leaper", "spitter"]),
                _w("WAVE 3", "Heavy hitters", ["brute", "bloater", "enforcer", "crusher", "acolyte", "outlaw"]),
                _w("WAVE 4", "No mercy!", ["leaper", "runner", "outlaw", "drone", "mage", "spitter", "rifleman", "trooper"]),
                _w("FINAL BOSS", "DARK ANAKIN", ["darkanakin"], True)]),
]

ULTS = {
    "john": dict(name="HARISSA APOCALYPSE", col=(255, 140, 40), strike="meteor", dmg=11, fdmg=75, fsprite="nuke", fscale=5.6, ftext="APOCALYPSE!!"),
    "jane": dict(name="SOLAR JUDGEMENT", col=(120, 205, 255), strike="bolt", dmg=11, fdmg=75, fsprite="blue_big", fscale=4.6, ftext="JUDGEMENT!!"),
}
ULT_T0, ULT_T1, ULT_T2, ULT_T3 = 58, 112, 34, 56

MOVE_HELP = [
    ("Z  Z  Z", "Triple strike chain  (3rd hit knocks them down)"),
    ("UP + Z", "Launcher - then JUMP and press Z for air combos"),
    ("DOWN + Z (air)", "Dive slam shockwave  (after a launcher = METEOR SPICE)"),
    ("X", "Fireball / light orb    (X with 5+ combo = COMBO BREAKER)"),
    ("DOWN + X", "PILLARS - fire / lightning columns erupt in front of you"),
    ("UP + X", "RISING PHOENIX - big flaming launcher"),
    ("SHIFT, then X", "COMET CHARGE - invincible rush ending in an explosion"),
    ("X in the air", "METEOR SHOT - diagonal blast that explodes on the ground"),
    ("SPACE x2", "Double jump"),
    ("SHIFT", "Dash - invincible. Dash THROUGH an attack = PERFECT DODGE (slow motion)"),
    ("C", "Special move  (needs 50 energy, fills when you hit)"),
    ("R / Q", "ULTIMATE - cinematic zoom attack when the ULT bar is full"),
    ("Combo", "More hits in a row = more damage and a higher rank. Don't get hit!"),
]


def chapter_bg(ch):
    k = ("chbg", ch["key"])
    if k in _bg_cache: return _bg_cache[k]
    if ch.get("bg_file"):
        b = img(ch["bg_file"], dirs=["maps"])
        if b.get_size() != (W, H): b = pygame.transform.scale(b, (W, H))
        wide = pygame.Surface((W * 3, H)).convert()
        wide.blit(b, (0, 0)); wide.blit(pygame.transform.flip(b, True, False), (W, 0)); wide.blit(b, (2 * W, 0))
        fc = ch.get("floor", (0, 0, 0)); fh = 190
        strip = pygame.Surface((W * 3, fh), pygame.SRCALPHA)
        for i in range(fh):
            pygame.draw.line(strip, (*fc, int(185 * (i / fh) ** 1.4)), (0, i), (W * 3, i))
        wide.blit(strip, (0, H - fh))
    else:
        b = img("tataouine_bg.png")
        wide = pygame.transform.smoothscale(b, (int(b.get_width() * H / b.get_height()), H)).convert()
    _bg_cache[k] = wide
    return wide


def make_decor(ch, world_w):
    rocks = [img("%s_%d.png" % (ch["decor"], i), dirs=["decor"]) for i in (1, 2, 3)]
    rnd = random.Random(ch["num"] * 77); items = []; x = rnd.uniform(200, 500)
    while x < world_w - 100:
        r = rnd.choice(rocks); sc = rnd.choice((2.6, 3.4, 4.2))
        items.append((x, pygame.transform.scale(r, (max(1, int(r.get_width() * sc)), max(1, int(r.get_height() * sc))))))
        x += rnd.uniform(380, 900)
    return items


def ease(x):
    x = clamp(x, 0.0, 1.0); return x * x * (3 - 2 * x)



class FightScene(Scene):
    def __init__(self, game, chapter=0, vs=False, final=False, net=None):
        super().__init__(game)
        self.net = net                                                # netplay.Lockstep when playing online
        if net: random.seed(net.seed)                                 # identical start state on both devices
        self.ci = chapter; self.ch = CHAPTERS[chapter]; self.waves = self.ch["waves"]
        self.bg = chapter_bg(self.ch); self.world_w = self.bg.get_width()
        self.world = pygame.Surface((W, H)).convert(); self.zbuf = None
        self.vs = bool(vs and game.mp); self.final = final; mp = game.mp
        if mp:
            self.player = Player(mp["chars"][0], game.blessing, game.start_energy)
            self.player2 = Player(mp["chars"][1], game.blessing, game.start_energy)
            self.player2.pid = 2; self.player2.tag = ("P2", P_COL[2]); self.player.tag = ("P1", P_COL[1])
        else:
            self.player = Player(game.char, game.blessing, game.start_energy); self.player2 = None
        self.players = [p for p in (self.player, self.player2) if p]
        self.presses2 = []; self.vs_state = "intro"; self.vs_t = 0; self.vs_wins = [0, 0]; self.vs_round = 1; self.vs_winner = 0; self.vs_over = False
        self.vs_start = (0, 0)
        self.enemies = []; self.projs = []; self.pickups = []; self.hazards = []; self.fx = Effects()
        self.sched = []; self.sched_real = []; self.ult = None; self.zoom = 1.0
        self.cam = 0.0; self.tick = 0; self.stop = 0; self.slow = 0; self.tokens = 0; self.max_tokens = 2
        self.combo = 0; self.combo_t = 0; self.max_combo = 0; self.combo_pop = 0.0; self.score = 0; self.kills = 0
        self.hp_scale = 1.7 if (self.player2 and not self.vs) else 1.0
        self.wave = -1; self.queue = []; self.spawn_t = 0; self.state = "intro"; self.timer = 150
        if self.player2 and self.vs:                                  # versus arena: both start with full, equal stats
            cx = self.world_w / 2.0; self.vs_start = (cx - 430, cx + 430)
            self.cam = clamp(cx - W / 2, 0, self.world_w - W)
            for p, x, fc in ((self.player, cx - 430, 1), (self.player2, cx + 430, -1)):
                p.maxhp = 300; p.hp = 300; p.hp_trail = 300.0; p.dmg_mult = 1.0; p.energy = 0.0; p.ult_meter = 0.0; p.x = x; p.face = fc
        elif self.player2:
            self.player.x = 360.0; self.player2.x = 540.0
        self.banner = ("CHAPTER %d" % self.ch["num"], self.ch["name"], 140, 140); self.paused = False; self.pause_sel = 0; self.dmg_taken = 0
        self.presses = []; self.override_held = None; self.end_t = 0; self.special_shown = False; self.ult_shown = False
        self.amb_kind = self.ch["amb"]
        self.sand = [[random.uniform(0, W), random.uniform(0, H), random.uniform(6, 14), random.uniform(1, 3)] for _ in range(90 if self.amb_kind == "snow" else 50)]
        self.vig = self._make_vignette(self.ch["vig"]); self.time = 0; self.boss = None
        self.bd = None; self.bd_pending = None; self.boss_dead = False
        self.needs_boss = any(w.get("boss") for w in self.waves) and not self.vs
        g = self.ch.get("grade")
        self.grade = None
        if g:
            self.grade = pygame.Surface((W, H), pygame.SRCALPHA); self.grade.fill(g)
        self.decor = make_decor(self.ch, self.world_w)
        self.portrait = self._make_portrait(); self.portrait2 = self._make_portrait(self.player2) if self.player2 else None
        self.ovl = None
        if self.vs:
            self.banner = ("THE LEGENDARY DUEL" if final else "VERSUS", "ROUND 1", 120, 120)
        audio.music("boss.mp3" if self.vs else self.ch["music"], True, 1.0)
        # -- online play state
        self.net_held = {1: dict(left=False, right=False, up=False, down=False), 2: dict(left=False, right=False, up=False, down=False)}
        self.loc_presses = []; self.net_menu = False; self.net_over = False
        if net: self.net_rng = random.getstate()                      # restored on the first simulated frame
        if touch: touch.pause_label = "MENU" if net else "PAUSE"

    @staticmethod
    def _make_vignette(col=(25, 8, 0)):
        v = pygame.Surface((W, H), pygame.SRCALPHA); n = 16
        for i in range(n):
            a = int(120 * (1 - i / n) ** 2.2)
            pygame.draw.rect(v, (*col, a), (i * 14, i * 9, W - i * 28, H - i * 18), 14, border_radius=40)
        return v

    def _make_portrait(self, pl=None):
        s, _, _ = (pl or self.player).A["idle"].get(0)
        crop = s.subsurface((0, 0, s.get_width(), int(s.get_height() * .45))).copy()
        sc = 112 / max(crop.get_height(), crop.get_width())
        return pygame.transform.scale(crop, (int(crop.get_width() * sc) + 1, int(crop.get_height() * sc) + 1))

    # -- helpers used by entities -----------------------------------------------------------
    def on_screen(self, x): return self.cam - 60 < x < self.cam + W + 60

    def later(self, delay, fn, real=False):
        (self.sched_real if real else self.sched).append([delay, fn])

    def nearest_enemy(self, x, rng=9999):
        best = None; bd = rng
        for e in self.enemies:
            if e.hittable() or e.state == "down":
                d = abs(e.x - x)
                if d < bd: bd = d; best = e
        return best

    # -- combo ------------------------------------------------------------------------------
    def combo_hit(self, dmg):
        self.combo += 1; self.combo_t = 160; self.max_combo = max(self.max_combo, self.combo); self.combo_pop = 1.0
        self.score += int(dmg * (10 + self.combo * 2))
        names = {3: "NICE!", 6: "SPICY!", 10: "HARISSA HOT!", 15: "SUPER SPICY!!", 25: "LEGENDARY!!!", 40: "CULTURE KING!!!!"}
        if self.combo in names:
            self.fx.text(names[self.combo], self.player.x, self.player.y - 340, GOLD, 70, 75, -1.1)
            audio.play("pickup", .5)
            if self.combo >= 10:
                pl = self.player; self.fx.ring(pl.x, pl.y - 110, 380, GOLD, 26, 12, 0.8); self.fx.zoom_kick = max(self.fx.zoom_kick, .04)
                self.fx.boom("boom_round", pl.x, pl.y - 120, 1.8, 26)

    def combo_break(self):
        if self.combo >= 5:
            bonus = self.combo * 20; self.score += bonus
        self.combo = 0; self.combo_t = 0

    def grant_popup(self, pl):
        if pl.popup and not pl.popup_done:
            pl.popup_done = True; nm, bonus = pl.popup
            self.score += bonus; pl.energy = min(100, pl.energy + 8)
            if not self.ult: pl.ult_meter = min(100.0, pl.ult_meter + 5 + bonus / 60)
            self.fx.text(nm + "  +%d" % bonus, pl.x, pl.y - 380, (255, 120, 60), 56, 80, -1.0)

    # -- damage dealing ---------------------------------------------------------------------
    def player_hits(self, pl, mv):
        rect = pl.attack_rect(mv); rehit = mv.get("rehit"); hit = False
        for e in self.enemies:
            if not e.hittable(): continue
            last = pl.hit_ids.get(id(e))
            if last is not None and (not rehit or pl.mt - last < rehit): continue
            if rect.colliderect(e.hurtbox()):
                pl.hit_ids[id(e)] = pl.mt; self.hit_enemy(pl, e, mv); hit = True
        if self.vs:                                                   # versus: melee hits the other player
            t = self.rival(pl); last = pl.hit_ids.get(id(t))
            if t.state != "dead" and not (last is not None and (not rehit or pl.mt - last < rehit)) and rect.colliderect(t.hurtbox()):
                pl.hit_ids[id(t)] = pl.mt
                if self.vs_hit(pl, t, mv["dmg"], pl.x, bool(mv.get("launch")) or mv["dmg"] >= 24): hit = True
        return hit

    def hit_enemy(self, pl, e, mv, dirx=None):
        mult = (1 + min(self.combo, 30) * 0.02) * pl.dmg_mult
        dmg = max(1, int(round(mv["dmg"] * mult * random.uniform(.95, 1.05))))
        d = dirx if dirx is not None else (pl.face if not mv.get("aoe") else (1 if e.x >= pl.x else -1))
        kb = mv.get("kb", (6, 0))
        crit = mv.get("launch") or dmg >= 20
        res = e.take_hit(self, dmg, d * kb[0], kb[1], mv.get("stun", 16), mv.get("launch", False), mv.get("juggle", False))
        if not res: return
        hx = e.x - d * 20; hy = e.y - e.hh * .6
        self.fx.burst(hx, hy, 14 if crit else 8, speed=11 if crit else 8)
        spark = "boom_round" if pl.char == "john" else "blue_circle"
        self.fx.boom(spark, hx, hy, 1.5 if crit else .85, 26)
        if crit and not self.ult: self.fx.zoom_kick = max(self.fx.zoom_kick, .018)
        self.fx.text(str(dmg), e.x + random.uniform(-30, 30), e.y - e.hh - 20, GOLD if crit else WHITE, 56 if crit else 44, 45)
        self.stop = max(self.stop, mv.get("stop", 3)); self.fx.shake = max(self.fx.shake, mv.get("shake", 2))
        audio.play("heavy" if crit else "hit", .8)
        pl.energy = min(100, pl.energy + dmg * 0.5)
        if not self.ult:
            pl.ult_meter = min(100.0, pl.ult_meter + dmg * 0.22)
            if pl.ult_meter >= 100 and not self.ult_shown:
                self.ult_shown = True; self.fx.text("ULTIMATE READY  [R]", pl.x, pl.y - 330, (255, 220, 90), 54, 90)
                self.fx.ring(pl.x, pl.y - 110, 420, (255, 220, 90), 28, 12, 0.8); audio.play("pickup", .9)
            elif pl.ult_meter < 100: self.ult_shown = False
        if pl.energy >= SPECIAL_COST and not self.special_shown:
            self.special_shown = True; self.fx.text("SPECIAL READY!  [C]", pl.x, pl.y - 300, BLUE, 52, 70)
        elif pl.energy < SPECIAL_COST: self.special_shown = False
        self.combo_hit(dmg)
        if mv is pl.move: self.grant_popup(pl)
        if res == "kill": self.fx.burst(hx, hy, 22, speed=14)

    def hit_enemy_proj(self, pr, e):
        pl = getattr(pr, "owner", None) or self.player
        mv = dict(dmg=pr.dmg, kb=pr.kb, stun=pr.stun, launch=pr.launch, stop=4, shake=4)
        self.hit_enemy(pl, e, mv, dirx=1 if pr.vx > 0 else -1)

    def nova(self, pl, nv):
        self.fx.shake = 24; self.fx.flash = .5; self.fx.flash_color = (255, 190, 90); audio.play("boom")
        self.fx.zoom_kick = max(self.fx.zoom_kick, .09)
        self.fx.sprite(fx_art()["nova"], pl.x, pl.y - 130, 12)
        self.fx.boom("boom_big" if pl.char == "john" else "blue_big", pl.x, pl.y - 140, 1.9, 20)
        for r, c in ((nv["radius"], (255, 170, 50)), (nv["radius"] * .65, (255, 230, 120)), (nv["radius"] * .35, WHITE)):
            self.fx.ring(pl.x, pl.y - 12, r, c, 30, 18)
        self.fx.burst(pl.x, pl.y - 120, 50, ((255, 200, 80), (255, 120, 20), (255, 255, 255)), 18, (6, 13), (24, 44))
        self.grant_popup(pl)
        mv = dict(dmg=nv["dmg"], kb=nv["kb"], launch=True, stun=30, stop=10, shake=18, aoe=True)
        self.vs_aoe(pl, pl.x, nv["radius"], nv["dmg"])
        for e in list(self.enemies):
            if e.hittable() and abs(e.x - pl.x) < nv["radius"]:
                self.hit_enemy(pl, e, mv)

    def slam_land(self, pl):
        mv = pl.move or pl.MV["SLAM"]
        self.fx.ring(pl.x, pl.y - 10, 300, (255, 220, 140), 24, 14); self.fx.shake = max(self.fx.shake, 14); audio.play("slam")
        self.fx.burst(pl.x, pl.y - 10, 18, ((255, 210, 130), (255, 255, 255)), 12)
        self.fx.boom("impact", pl.x, pl.y - 70, 1.7, 24); self.fx.zoom_kick = max(self.fx.zoom_kick, .035)
        mm = dict(dmg=mv["dmg"] * 1.3, kb=(12, -17), launch=True, stun=26, stop=8, shake=12, aoe=True)
        self.vs_aoe(pl, pl.x, 300, mv["dmg"] * 1.3)
        for e in list(self.enemies):
            if e.hittable() and abs(e.x - pl.x) < 300 and e.on_ground:
                self.hit_enemy(pl, e, mm)
        pl.slam = False

    def blast(self, pl, x, spec):
        fire = spec["kind"] == "fire"; col = (255, 170, 60) if fire else (170, 225, 255)
        self.fx.boom("boom_big" if fire else "blue_big", x, pl.y - 120, 1.7 if fire else 1.5, 20)
        self.fx.ring(x, pl.y - 12, spec["radius"] * 1.2, col, 24, 14); self.fx.shake = max(self.fx.shake, 18)
        self.fx.zoom_kick = max(self.fx.zoom_kick, .06); self.fx.flash = max(self.fx.flash, .25); self.fx.flash_color = col
        self.fx.burst(x, pl.y - 100, 26, (col, (255, 255, 255)), 14); audio.play("boom")
        mv = dict(dmg=spec["dmg"], kb=(14, -22), launch=True, stun=28, stop=8, shake=14, aoe=True)
        self.vs_aoe(pl, x, spec["radius"], spec["dmg"])
        for e in list(self.enemies):
            if e.hittable() and abs(e.x - x) < spec["radius"] + e.hw: self.hit_enemy(pl, e, mv)

    def spawn_pillars(self, pl, pil):
        mv = dict(dmg=pil["dmg"], kb=(5, -20), launch=True, stun=30, stop=3, shake=8, aoe=True)
        self.grant_popup(pl)
        for i in range(pil["n"]):
            x = clamp(pl.x + pl.face * (pil["first"] + i * pil["gap"]), 80, self.world_w - 80)
            self.hazards.append(Hazard(self, x, pil["delay"] * (i + 1), pil["kind"], True, pil["dmg"], pil["r"], pl, mv))

    def perfect_dodge(self, pl):
        pl.pd_cd = 70; self.slow = max(self.slow, 45); pl.energy = min(100, pl.energy + 14)
        pl.ult_meter = min(100.0, pl.ult_meter + 7); pl.invuln = max(pl.invuln, 30); self.score += 150
        self.fx.text("PERFECT DODGE!", pl.x, pl.y - 330, (130, 220, 255), 52, 60, -1.1)
        self.fx.ring(pl.x, pl.y - 110, 300, (130, 220, 255), 24, 10, 0.9); self.fx.zoom_kick = max(self.fx.zoom_kick, .05)
        self.fx.flash = max(self.fx.flash, .14); self.fx.flash_color = (150, 220, 255); audio.play("pickup", .8)

    def aoe_on_player(self, e, radius, dmg, big=False, cy=(-140, 40)):
        cx = e.x + e.face * 60
        for p in self.players:
            if p.state != "dead" and abs(p.x - cx) < radius and p.y > GROUND - 140:
                p.take_hit(self, dmg, e.x, big)

    def spawn_player_proj(self, pl, pr):
        p = Projectile(pl.x + pl.face * pr["x"], pl.y + pr["y"], pl.face * pr["speed"], pr["dmg"], pr["kind"], True,
                       pr.get("kb", (8, -4)), pr.get("stun", 18), pr.get("pierce", False), pr.get("launch", False),
                       vy=pr.get("vy", 0.0), aoe=pr.get("aoe", 0))
        p.owner = pl; self.projs.append(p); self.grant_popup(pl)
        big = pr["kind"].endswith("big")
        self.fx.boom("boom_round" if pr["kind"].startswith("fire") else "blue_circle", p.x, p.y, 1.2 if big else .75, 24)
        if big: self.fx.zoom_kick = max(self.fx.zoom_kick, .03); self.fx.shake = max(self.fx.shake, 5)
        isf = pr["kind"].startswith("fire")
        self.fx.ring(p.x, p.y, 150 if big else 90, (255, 170, 60) if isf else (170, 215, 255), 14, 8, .8)
        self.fx.burst(p.x, p.y, 16 if big else 8, ((255, 230, 120), (255, 140, 40)) if isf else ((200, 230, 255), (255, 255, 255)), 8, (3, 7), (10, 20), 0.1)

    def spawn_enemy_proj(self, e, kind, speed, dmg, xoff, ground_y=-120, vy=0.0):
        self.projs.append(Projectile(e.x + e.face * xoff, e.y + ground_y, e.face * speed, dmg, kind, False, life=140, vy=vy))

    def boss_hazards(self, boss, atk):
        p = self.target_player(boss.x); ph = boss.phase(); R = random
        if atk == "storm":
            n = 4 + ph; xs = [p.x + (i - (n - 1) / 2) * R.uniform(170, 230) for i in range(n)]; R.shuffle(xs)
            for i, x in enumerate(xs):
                self.hazards.append(Hazard(self, clamp(x, 80, self.world_w - 80), 40 + i * 9, "bolt", False, 16, 95))
            self.fx.text("LIGHTNING!", boss.x, boss.y - boss.hh - 40, (190, 150, 255), 50, 50)
        elif atk == "meteor":
            n = 5 + ph
            for i in range(n):
                x = p.x + (p.vx * 12 if i == 0 else R.uniform(-700, 700))
                self.hazards.append(Hazard(self, clamp(x, 80, self.world_w - 80), 38 + i * 8, "meteor", False, 15, 125))
            self.fx.text("INCOMING!", boss.x, boss.y - boss.hh - 40, (255, 120, 60), 50, 50)
        elif atk == "eruption":
            n = 4 + ph
            for i in range(n):
                x = boss.x + boss.face * (220 + i * 210)
                self.hazards.append(Hazard(self, clamp(x, 80, self.world_w - 80), 36 + i * 8, "toxic", False, 13, 115))
            self.fx.text("ERUPTION!", boss.x, boss.y - boss.hh - 40, (120, 255, 120), 50, 50)

    def summon(self, boss):
        sm = boss.cfg.get("summons"); ph = boss.phase()
        kinds = sm[ph] if sm and ph in sm else (["acolyte", "acolyte"] if ph == 2 else ["mage", "leaper", "acolyte"])
        self.fx.text("REINFORCEMENTS!", boss.x, boss.y - boss.hh - 40, (255, 90, 60), 54, 60)
        for i, kd in enumerate(kinds):
            sx = clamp(boss.x + (-1 if i % 2 else 1) * (260 + 120 * i), 100, self.world_w - 100)
            en = Enemy(kd, sx, self); en.set("chase"); en.cd = 40; self.enemies.append(en)
            self.fx.ring(sx, GROUND - 10, 160, (200, 60, 255), 24, 10)
        self.fx.shake = 8; audio.play("boom", .6)

    def on_kill(self, e):
        self.kills += 1
        self.score += int(e.score * (1 + self.combo * .05))
        self.fx.text("+%d" % int(e.score * (1 + self.combo * .05)), e.x, e.y - e.hh - 60, (255, 230, 120), 40, 60)
        self.stop = max(self.stop, 9 if not e.boss else 20); self.fx.shake = max(self.fx.shake, 8)
        audio.play("ko", .7)
        if not self.ult:
            for _p in self.players: _p.ult_meter = min(100.0, _p.ult_meter + 3)
        dth = e.cfg.get("death"); big = e.boss
        if dth == "gas":
            self.fx.boom("gas", e.x, e.y - 110, 3.2 if big else 1.2, 18); self.fx.burst(e.x, e.y - 100, 14, ((110, 240, 110), (210, 255, 200)), 8)
        elif dth == "boom":
            self.fx.boom("boom_round", e.x, e.y - 110, 3.6 if big else 1.5, 22); self.fx.burst(e.x, e.y - 100, 16, ((255, 200, 90), (255, 255, 255)), 10)
            self.fx.shake = max(self.fx.shake, 12 if not big else 20)
        if e.boss:
            # the level can only end through the boss death cinematic (see begin_boss_cinematic)
            self.boss_dead = True; self.bd_pending = e
            self.stop = max(self.stop, 16); self.fx.flash = .7; self.fx.flash_color = WHITE; self.fx.shake = 24; self.fx.zoom_kick = .1
            self.fx.burst(e.x, e.y - 120, 70, ((255, 255, 255), (120, 180, 255), (255, 220, 100)), 20, (6, 14), (30, 60))
            for en in self.enemies:
                if en is not e and en.state != "dead": en.die(self, 0)
        elif random.random() < 0.16:
            self.pickups.append(Pickup(e.x))

    # -- ultimate ---------------------------------------------------------------------------
    def try_ult(self, pl):
        if self.ult or pl.state in ("dead", "hurt", "down"): return False
        if self.state not in ("wave", "clear"): return False
        if pl.ult_meter < 100:
            self.fx.text("ULT %d%%" % int(pl.ult_meter), pl.x, pl.y - 270, (255, 210, 120), 30, 24); return False
        U = ULTS[pl.char]
        self.ult = dict(t=0, phase=0, U=U, pl=pl); pl.ult_meter = 0.0; self.ult_shown = False
        pl.state = "ult"; pl.ult_t = 0; pl.move = None; pl.slam = False; pl.vx = 0; pl.vy = 0; pl.invuln = 999; pl.buf = None
        self.presses = []; audio.play("special"); audio.play("boom", .6)
        self.fx.flash = .55; self.fx.flash_color = U["col"]; self.combo_t = max(self.combo_t, 160)
        return True

    def ult_zoom(self):
        u = self.ult; t = u["t"]; ph = u["phase"]
        if ph == 0: return 1.0 + 0.7 * ease(t / ULT_T0)
        if ph == 1: return 1.7 - 0.38 * ease(t / 22) + 0.035 * math.sin(t * .6)
        if ph == 2: return 1.32 + 0.95 * ease(t / ULT_T2)
        return 2.27 - 1.27 * ease(t / ULT_T3)

    def zoom_focus(self):
        pl = self.ult["pl"] if self.ult else self.player
        if self.bd:
            b = self.bd["boss"]; return (b.x - self.cam, b.y - 170)
        if self.ult and self.ult["phase"] in (2, 3):
            return (pl.x + pl.face * 260 - self.cam, pl.y - 230)
        return (pl.x - self.cam, pl.y - 150)

    def ult_strike(self, pl, U):
        tg = [e for e in self.enemies if e.hittable() and self.on_screen(e.x) and abs(e.x - pl.x) < 1200]
        if tg and random.random() < .8:
            x = random.choice(tg).x + random.uniform(-40, 40)
        else:
            x = pl.x + pl.face * random.uniform(-250, 950)
        x = clamp(x, 80, self.world_w - 80)
        mv = dict(dmg=U["dmg"], kb=(4, -18), launch=True, stun=26, stop=1, shake=7, aoe=True)
        self.hazards.append(Hazard(self, x, 11, U["strike"], True, U["dmg"], 150, pl, mv))

    def ult_finale(self, pl, U):
        fxp = clamp(pl.x + pl.face * 330, 100, self.world_w - 100)
        self.fx.boom(U["fsprite"], fxp, GROUND - 330, U["fscale"], 13)
        self.fx.boom("boom_mush" if pl.char == "john" else "impact", fxp, GROUND - 200, 3.6, 16)
        for r, c in ((900, U["col"]), (620, (255, 255, 255)), (380, U["col"])):
            self.fx.ring(fxp, GROUND - 12, r, c, 34, 22)
        self.fx.burst(fxp, GROUND - 200, 80, (U["col"], (255, 255, 255), (255, 230, 150)), 24, (7, 15), (30, 60))
        self.fx.flash = 1.0; self.fx.flash_color = WHITE; self.fx.shake = 44; self.slow = 60
        audio.play("boom"); audio.play("ko"); audio.play("special")
        self.fx.text(U["ftext"], pl.x, pl.y - 420, U["col"], 96, 90, -.8)
        mv = dict(dmg=U["fdmg"], kb=(20, -26), launch=True, stun=40, stop=14, shake=30, aoe=True)
        for e in list(self.enemies):
            if e.hittable() and self.on_screen(e.x): self.hit_enemy(pl, e, mv)

    def update_ult(self):
        u = self.ult; pl = u["pl"]; U = u["U"]; u["t"] += 1; t = u["t"]; ph = u["phase"]
        if ph == 0:
            if t % 5 == 1: self.fx.ring(pl.x, pl.y - 100, 260, U["col"], 22, 10, 0.8)
            if t % 7 == 1: self.fx.boom("fire" if pl.char == "john" else "blue_oval", pl.x + random.uniform(-90, 90), GROUND + 10,
                                        3.0 if pl.char == "john" else 1.4, 16, "bottom" if pl.char == "john" else "center",
                                        128 if pl.char == "john" else 256)
            self.fx.shake = max(self.fx.shake, 3 + t * .05)
            if t >= ULT_T0: u["phase"] = 1; u["t"] = 0; self.fx.flash = .45; self.fx.flash_color = U["col"]; audio.play("boom", .7)
        elif ph == 1:
            if t % 5 == 1: self.ult_strike(pl, U)
            if t >= ULT_T1: u["phase"] = 2; u["t"] = 0
        elif ph == 2:
            if t == 1: audio.play("special"); self.fx.ring(pl.x, pl.y - 100, 500, WHITE, 26, 14, 0.8)
            self.fx.shake = max(self.fx.shake, 6)
            if t >= ULT_T2: self.ult_finale(pl, U); u["phase"] = 3; u["t"] = 0
        else:
            if t >= ULT_T3:
                self.ult = None; pl.state = "idle" if pl.on_ground else "jump"; pl.invuln = 70; pl.ult_t = 0

    def draw_ult_overlay(self, surf):
        u = self.ult; U = u["U"]; t = u["t"]; ph = u["phase"]; col = U["col"]
        k = ease(t / 18) if ph == 0 else (1.0 if ph in (1, 2) else 1 - ease(t / 20))
        if self.ovl is None: self.ovl = pygame.Surface((W, H), pygame.SRCALPHA)
        o = self.ovl
        dark = int((130 if ph in (0, 1) else 60 if ph == 2 else 40) * k)
        o.fill((0, 0, 0, dark))
        if ph in (0, 2) or (ph == 1 and t < 14):
            fxp, fyp = self.zoom_focus(); cnt = 36 if ph == 0 else 52
            for i in range(cnt):
                a = random.uniform(0, math.tau); r0 = random.uniform(380, 640); r1 = r0 + random.uniform(300, 700)
                pygame.draw.line(o, (255, 255, 255, random.randint(70, 170)), (fxp + math.cos(a) * r0, fyp + math.sin(a) * r0 * .6),
                                 (fxp + math.cos(a) * r1, fyp + math.sin(a) * r1 * .6), random.randint(2, 6))
        bar_h = int(120 * k)
        pygame.draw.rect(o, (0, 0, 0, 255), (0, 0, W, bar_h)); pygame.draw.rect(o, (0, 0, 0, 255), (0, H - bar_h, W, bar_h))
        surf.blit(o, (0, 0))
        if ph == 0:
            sl = ease(t / 20); sx = lerp(-900, 0, sl) if t < ULT_T0 - 10 else lerp(0, 1300, ease((t - ULT_T0 + 10) / 10))
            band = pygame.Surface((W, 190), pygame.SRCALPHA); band.fill((*col, 150)); surf.blit(band, (0, H // 2 - 330))
            text(surf, "ULTIMATE", font(54), WHITE, (W // 2 + sx - 20, H // 2 - 320), "midtop", outline=4)
            text(surf, U["name"], font(124), WHITE, (W // 2 + sx, H // 2 - 255), "midtop", outline=8)
            surf.blit(self.portrait2 if (self.player2 and u["pl"] is self.player2) else self.portrait, (180 + sx, H // 2 - 330 + 40))
        elif ph == 2 and t > ULT_T2 - 12:
            f = pygame.Surface((W, H)); f.fill(WHITE); f.set_alpha(int(210 * (t - (ULT_T2 - 12)) / 12)); surf.blit(f, (0, 0))

    # -- waves ------------------------------------------------------------------------------
    def spawn_one(self):
        kind = self.queue.pop(0)
        side = random.choice((-1, 1))
        x = self.cam + (-170 if side < 0 else W + 170)
        if x < 60 or x > self.world_w - 60: x = self.cam + (W + 170 if side < 0 else -170)
        x = clamp(x, 60, self.world_w - 60)
        e = Enemy(kind, x, self); self.enemies.append(e)
        if e.boss:
            self.boss = e; e.x = clamp(self.player.x + (700 if self.player.x < self.world_w - 900 else -700), 100, self.world_w - 100)
            self.fx.shake = 14; audio.play("boom")

    def start_wave(self, n):
        self.wave = n; w = self.waves[n]; self.queue = list(w["spawn"]); self.state = "wave"; self.spawn_t = 10
        if w.get("boss"): audio.music("boss.mp3", True, 1.0)
        self.banner = (w["title"], w["sub"], 110, 110)
        self.cap = 5 if not w.get("boss") else 4

    def update_waves(self):
        if self.vs: self.update_vs(); return
        if self.state == "intro":
            self.timer -= 1
            if self.timer <= 0: self.start_wave(0)
        elif self.state == "wave":
            alive = len([e for e in self.enemies if e.state != "dead"])
            self.spawn_t -= 1
            if self.queue and alive < self.cap and self.spawn_t <= 0:
                self.spawn_one(); self.spawn_t = 55 if not self.waves[self.wave].get("boss") else 10
            if self.bd_pending: return                       # boss cinematic is about to start
            if not self.queue and alive == 0 and self.waves[self.wave].get("boss"):
                if self.boss_dead: self.state = "victory"; self.end_t = 0     # only reachable if the cinematic was skipped
            elif not self.queue and alive == 0:
                self.state = "clear"; self.timer = 150
                self.banner = ("WAVE CLEARED!", "", 100, 100); audio.play("true")
                self.score += 300 * (self.wave + 1)
                if self.wave % 2 == 1: self.pickups.append(Pickup(self.player.x + 250)); self.pickups.append(Pickup(self.player.x - 250))
                else: self.pickups.append(Pickup(self.player.x + 250))
                for _p in self.players:
                    if _p.state == "dead": _p.revive(.5)                 # a fallen team mate comes back between waves
                    _p.energy = min(100, _p.energy + 25)
                    _p.hp = min(_p.maxhp, _p.hp + int(_p.maxhp * .08))
        elif self.state == "clear":
            self.timer -= 1
            if self.timer <= 0:
                if self.wave + 1 >= len(self.waves):
                    if self.needs_boss and not self.boss_dead:      # never let the level end without killing the boss
                        self.start_wave(max(i for i, w in enumerate(self.waves) if w.get("boss")))
                    else: self.state = "victory"; self.end_t = 0
                else: self.start_wave(self.wave + 1)

    # -- input ------------------------------------------------------------------------------
    KEYS = {pygame.K_z: "light", pygame.K_j: "light", pygame.K_x: "heavy", pygame.K_k: "heavy", pygame.K_c: "special", pygame.K_l: "special",
            pygame.K_SPACE: "jump", pygame.K_LSHIFT: "dash", pygame.K_RSHIFT: "dash", pygame.K_v: "dash",
            pygame.K_r: "ult", pygame.K_q: "ult", pygame.K_u: "ult"}

    def get_held(self, pid=0):
        if self.net: return self.net_held[2 if pid == 2 else 1]
        return self.local_held(pid)

    def push_press(self, name):                                       # used by the touch buttons
        lst = self.loc_presses if self.net else self.presses
        if len(lst) < 4: lst.append(name)

    def toggle_pause(self):
        if self.net: self.net_menu = not self.net_menu; return
        self.paused = not self.paused; self.pause_sel = 0

    def local_held(self, pid=0):
        if pid:
            k = pygame.key.get_pressed()
            if pid == 1: return dict(left=k[pygame.K_a], right=k[pygame.K_d], up=k[pygame.K_w], down=k[pygame.K_s])
            return dict(left=k[pygame.K_LEFT], right=k[pygame.K_RIGHT], up=k[pygame.K_UP], down=k[pygame.K_DOWN])
        if touch and touch.override_held() is not None: return touch.override_held()
        if self.override_held is not None: return self.override_held
        k = pygame.key.get_pressed()
        return dict(left=k[pygame.K_LEFT] or k[pygame.K_a], right=k[pygame.K_RIGHT] or k[pygame.K_d],
                    up=k[pygame.K_UP] or k[pygame.K_w], down=k[pygame.K_DOWN] or k[pygame.K_s])

    def event(self, e):
        if touch and touch.handle(e, self): return
        if self.net: self.net_event(e); return
        if e.type == pygame.KEYDOWN:
            if e.key in (pygame.K_ESCAPE, pygame.K_p):
                self.paused = not self.paused; self.pause_sel = 0
                if self.paused: audio.play("confirm")
                return
            if self.paused:
                if e.key in (pygame.K_UP, pygame.K_DOWN, pygame.K_w, pygame.K_s): self.pause_sel = 1 - self.pause_sel; audio.play("hover", .5)
                elif e.key in (pygame.K_RETURN, pygame.K_SPACE): self.pause_pick()
                return
            if self.player2:
                if e.key in KEYS_P1 and len(self.presses) < 4: self.presses.append(KEYS_P1[e.key])
                if e.key in KEYS_P2 and len(self.presses2) < 4: self.presses2.append(KEYS_P2[e.key])
            elif e.key in self.KEYS and len(self.presses) < 4: self.presses.append(self.KEYS[e.key])
        elif self.paused and e.type == pygame.MOUSEMOTION:
            for i, r in enumerate(self.pause_rects()):
                if r.collidepoint(e.pos) and self.pause_sel != i: self.pause_sel = i; audio.play("hover", .5)
        elif self.paused and e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            for i, r in enumerate(self.pause_rects()):
                if r.collidepoint(e.pos): self.pause_sel = i; self.pause_pick()
        elif e.type == pygame.WINDOWFOCUSLOST:
            self.paused = True

    def pause_rects(self): return [pygame.Rect(W // 2 - 260, 850, 240, 70), pygame.Rect(W // 2 + 20, 850, 240, 70)]

    def pause_pick(self):
        audio.play("confirm")
        if self.pause_sel == 0: self.paused = False
        else: self.game.go(MenuScene(self.game))

    # -- ambient ----------------------------------------------------------------------------
    def amb_update(self):
        k = self.amb_kind
        for s in self.sand:
            if k == "sand":
                s[0] -= s[2] * .5; s[1] += math.sin((s[0] + s[1]) * .01) * .4
            elif k == "ash":
                s[1] -= s[3] * .45; s[0] += math.sin(s[1] * .02 + s[2]) * .8
            elif k == "ember":
                s[0] += s[2] * .35; s[1] -= .7 + s[3] * .2
            elif k == "spark":
                s[1] -= s[2] * .45; s[0] += math.sin(s[1] * .05) * 1.2
            else:
                s[1] += s[3] * .9 + 1.2; s[0] -= s[2] * .1 + math.sin(s[1] * .01) * .6
            if s[0] < -10: s[0] = W + 10; s[1] = random.uniform(0, H)
            if s[0] > W + 10: s[0] = -10; s[1] = random.uniform(0, H)
            if s[1] < -10: s[1] = H + 10; s[0] = random.uniform(0, W)
            if s[1] > H + 10: s[1] = -10; s[0] = random.uniform(0, W)

    def amb_draw(self, surf):
        k = self.amb_kind
        for s in self.sand:
            x, y = int(s[0]), int(s[1])
            if k == "sand": pygame.draw.rect(surf, (235, 200, 140), (x, y, int(s[3] * 2), 2))
            elif k == "ash": pygame.draw.circle(surf, (175, 150, 205), (x, y), int(s[3]))
            elif k == "ember": pygame.draw.circle(surf, (255, 150 + int(s[3] * 20), 70), (x, y), max(1, int(s[3])))
            elif k == "spark": pygame.draw.rect(surf, (255, 220, 120), (x, y, 3, int(s[3] * 3)))
            else: pygame.draw.circle(surf, (240, 248, 255), (x, y), max(1, int(s[3])))

    # -- online play ------------------------------------------------------------------------
    def net_event(self, e):
        if e.type == pygame.KEYDOWN:
            if e.key in (pygame.K_ESCAPE, pygame.K_p): self.net_menu = not self.net_menu; audio.play("confirm"); return
            if self.net_menu:
                if e.key in (pygame.K_RETURN, pygame.K_SPACE): self.net_leave()
                return
            if e.key in self.KEYS and len(self.loc_presses) < 4: self.loc_presses.append(self.KEYS[e.key])
        elif self.net_menu and e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            r_stay, r_leave = self.pause_rects()
            if r_stay.collidepoint(e.pos): self.net_menu = False; audio.play("confirm")
            elif r_leave.collidepoint(e.pos): self.net_leave()

    def net_leave(self):
        self.net.finished = True; self.net_over = True
        self.game.net_leave()

    def net_begin_frame(self):
        """lockstep gate: returns False when this frame must wait for the other device"""
        ls = self.net
        if ls.finished or self.net_over:                              # match is over, just let the scene fade out
            self.net_held = {1: dict(left=False, right=False, up=False, down=False), 2: dict(left=False, right=False, up=False, down=False)}
            return True
        ls.pump()
        if ls.peer_left:
            self.net_over = True; ls.finished = True; self.game.net_lost("The other player left the match"); return False
        if not ls.seeded: random.setstate(self.net_rng); ls.seeded = True
        from netplay import pack_held, unpack_held
        if ls.submitted != ls.frame:
            ls.submit(pack_held(self.local_held()), self.loc_presses); self.loc_presses = []
        if not ls.ready():
            ls.stall += 1
            if ls.stall > 900 or ls.link.silent_for() > 10:
                self.net_over = True; ls.finished = True; self.game.net_lost("Connection lost"); 
            return False
        ls.stall = 0
        ls.snapshot_out(self.players); ls.snapshot_in(self.players)
        (h1, p1), (h2, p2) = ls.inputs()
        self.net_held = {1: unpack_held(h1), 2: unpack_held(h2)}
        for nm in p1:
            if len(self.presses) < 4: self.presses.append(nm)
        for nm in p2:
            if len(self.presses2) < 4: self.presses2.append(nm)
        return True

    def net_overlay(self, surf):
        ls = self.net
        if ls.stall > 20 and not ls.finished:
            d = pygame.Surface((W, 120), pygame.SRCALPHA); d.fill((0, 0, 0, 170)); surf.blit(d, (0, H // 2 - 60))
            text(surf, "WAITING FOR THE OTHER PLAYER...", font(56), GOLD, (W // 2, H // 2), "center", outline=4)
        if self.time < 420:
            me = 1 if ls.host else 2
            text(surf, "YOU ARE  P%d  (%s)" % (me, self.players[me - 1].name), font(40), P_COL[me], (W // 2, 176 if self.vs else 130), "midtop", outline=4,
                 alpha=int(255 * clamp((420 - self.time) / 60.0, 0, 1)))
        if self.net_menu:
            d = pygame.Surface((W, H), pygame.SRCALPHA); d.fill((0, 0, 0, 175)); surf.blit(d, (0, 0))
            text(surf, "LEAVE THE MATCH?", font(100), GOLD, (W // 2, 330), "center", outline=6)
            text(surf, "The game keeps running for your friend", nfont(34, True), WHITE, (W // 2, 440), "center", 3)
            for i, (r, lab) in enumerate(zip(self.pause_rects(), ("STAY", "LEAVE"))):
                rrect(surf, (255, 190, 60) if i == 0 else (120, 50, 60), r, 18); rrect(surf, WHITE, r, 18, 3)
                text(surf, lab, font(42), BLACK if i == 0 else WHITE, r.center, "center", shadow=0)

    # -- update -----------------------------------------------------------------------------
    def update(self):
        if not self.net: return self._update_sim()
        if not self.net_begin_frame(): return
        self._update_sim()
        if not self.net.finished: self.net.advance()

    def _update_sim(self):
        if self.paused: return
        pl = self.player
        self.fx.update(world=not self.bd)
        self.combo_pop = max(0, self.combo_pop - .08)
        self.amb_update()
        self._camera()
        for s in self.sched_real: s[0] -= 1
        for s in [s for s in self.sched_real if s[0] <= 0]: s[1]()
        self.sched_real = [s for s in self.sched_real if s[0] > 0]
        tz = 1.0 + self.fx.zoom_kick
        if self.ult: tz = self.ult_zoom()
        if self.bd: tz = self.bd_zoom()
        self.zoom = lerp(self.zoom, tz, .35 if self.ult else .08 if self.bd else .22)
        if self.ult and self.ult["phase"] == 0:
            self.presses = []; self.update_ult(); return
        if self.bd or (self.bd_pending and not self.ult and any(p.state != "dead" for p in self.players)):
            if not self.bd: self.begin_boss_cinematic()
            self.update_boss_cinematic(); return
        if self.stop > 0:
            self.stop -= 1; self.presses = self.presses[-2:]; self.presses2 = self.presses2[-2:]; return
        if self.slow > 0:
            self.slow -= 1
            if self.slow % 3: return
        self.tick += 1; self.time += 1
        for p in self.players:
            held, pr = self.input_for(p)
            p.update(self, held, pr)
        if self.player2: self.lock_players()
        for e in self.enemies: e.update(self)
        self.enemies = [e for e in self.enemies if not (e.state == "dead" and e.alpha <= 0)]
        for p in self.projs: p.update(self)
        self.projs = [p for p in self.projs if not p.dead]
        for h in self.hazards: h.update(self)
        self.hazards = [h for h in self.hazards if not h.dead]
        for k in self.pickups: k.update(self)
        self.pickups = [k for k in self.pickups if not k.dead]
        for s in self.sched: s[0] -= 1
        for s in [s for s in self.sched if s[0] <= 0]: s[1]()
        self.sched = [s for s in self.sched if s[0] > 0]
        if self.combo_t > 0:
            self.combo_t -= 1
            if self.combo_t == 0: self.combo_break()
        if self.ult: self.update_ult()
        self.update_waves()
        # end conditions
        if not self.vs and all(p.state == "dead" and p.dead_t > 120 for p in self.players) and self.state != "over":
            self.state = "over"; self.game.fight_over(self)
        if self.state == "victory":
            self.end_t += 1
            if self.end_t > 150 and (self.boss_dead or not self.needs_boss) and not getattr(self, "_won", False):
                self._won = True; self.game.chapter_done(self)

    # -- multiplayer helpers ----------------------------------------------------------------
    def target_player(self, x):
        best = self.player; bd = 1e9
        for p in self.players:
            if p.state == "dead": continue
            d = abs(p.x - x)
            if d < bd: bd = d; best = p
        return best

    def rival(self, pl): return self.player2 if pl is self.player else self.player

    def input_for(self, p):
        if self.vs and self.vs_state != "fight":                      # frozen during intro / round end
            self.presses = []; self.presses2 = []
            return dict(left=False, right=False, up=False, down=False), []
        if self.player2 is None:
            pr = self.presses; self.presses = []; return self.get_held(), pr
        if p.pid == 2:
            pr = self.presses2; self.presses2 = []; return self.get_held(2), pr
        pr = self.presses; self.presses = []; return self.get_held(1), pr

    def lock_players(self):                                           # nobody can leave the screen
        for p in self.players:
            if p.state != "dead": p.x = clamp(p.x, self.cam + 90, self.cam + W - 90)

    def vs_hit(self, pl, t, dmg, from_x, big=False):
        if t.state == "dead" or self.vs_state != "fight": return False
        dmg = max(1, int(round(dmg * VS_DMG * pl.dmg_mult * random.uniform(.95, 1.05))))
        if not t.take_hit(self, dmg, from_x, big): return False
        d = 1 if t.x >= from_x else -1; hx = t.x - d * 20; hy = t.y - 120
        self.fx.burst(hx, hy, 14 if big else 8, speed=11 if big else 8)
        self.fx.boom("boom_round" if pl.char == "john" else "blue_circle", hx, hy, 1.5 if big else .85, 26)
        self.stop = max(self.stop, 8 if big else 4); self.fx.shake = max(self.fx.shake, 8 if big else 3)
        audio.play("heavy" if big else "hit", .8)
        pl.energy = min(100, pl.energy + dmg * .5)
        if t.state == "dead": self.slow = max(self.slow, 70); self.fx.flash = .5; self.fx.flash_color = WHITE
        return True

    def vs_aoe(self, pl, cx, radius, dmg, big=True):
        if not self.vs: return
        t = self.rival(pl)
        if t.state != "dead" and abs(t.x - cx) < radius + 38 and t.y > GROUND - 420: self.vs_hit(pl, t, dmg, cx, big)

    def update_vs(self):
        s = self.vs_state; self.vs_t += 1
        if s == "intro":
            if self.vs_t > (120 if self.vs_round == 1 else 70):
                self.vs_state = "fight"; self.vs_t = 0; self.banner = ("FIGHT!", "", 50, 50); audio.play("special", .6)
        elif s == "fight":
            a, b = self.player, self.player2
            if a.state == "dead" or b.state == "dead":
                if a.state == "dead" and b.state == "dead": w = 0 if a.dead_t <= b.dead_t else 1
                else: w = 1 if a.state == "dead" else 0
                self.vs_winner = w; self.vs_wins[w] += 1; self.vs_state = "round_end"; self.vs_t = 0
                self.banner = ("K.O.!", "%s wins round %d" % (self.players[w].name, self.vs_round), 150, 150); audio.play("true")
        elif s == "round_end":
            if self.vs_t > 180:
                if self.vs_wins[self.vs_winner] >= 2:
                    if not self.vs_over: self.vs_over = True; self.game.vs_done(self)
                else: self.vs_reset_round()

    def vs_reset_round(self):
        self.vs_round += 1
        for p, x, fc in ((self.player, self.vs_start[0], 1), (self.player2, self.vs_start[1], -1)):
            p.revive(1.0, x); p.face = fc; p.energy = min(p.energy, 50.0)
        self.projs = []; self.hazards = []; self.slow = 0; self.vs_state = "intro"; self.vs_t = 0
        self.banner = ("ROUND %d" % self.vs_round, "%d  -  %d" % tuple(self.vs_wins), 100, 100)

    def draw_vs_hud(self, surf):
        for i, p in enumerate(self.players):
            right = i == 1; col = P_COL[i + 1]; x0 = W - 40 - 780 if right else 40
            pan = pygame.Surface((780, 150), pygame.SRCALPHA); rrect(pan, (10, 10, 18, 190), pan.get_rect(), 20); rrect(pan, col, pan.get_rect(), 20, 3)
            surf.blit(pan, (x0, 20))
            text(surf, "P%d  %s" % (i + 1, p.name), font(36), col, (x0 + 30, 28), outline=3)
            for r in range(2):
                pygame.draw.circle(surf, GOLD if self.vs_wins[i] > r else (60, 55, 70), (x0 + 700 - r * 44, 50), 15)
                pygame.draw.circle(surf, WHITE, (x0 + 700 - r * 44, 50), 15, 2)
            bar(surf, (x0 + 30, 78, 720, 34), p.hp / p.maxhp, (210, 45, 55) if p.hp > p.maxhp * .3 else (255, 70, 40), trail=p.hp_trail / p.maxhp)
            text(surf, "%d / %d" % (p.hp, p.maxhp), nfont(24, True), WHITE, (x0 + 390, 95), "center", 2)
            ready = p.energy >= SPECIAL_COST
            bar(surf, (x0 + 30, 120, 460, 20), p.energy / 100, (255, 190, 60) if ready else (80, 170, 255))
            text(surf, "SPECIAL READY!" if ready else "ENERGY", nfont(20, True), GOLD if ready else (170, 200, 255), (x0 + 505, 120))
        text(surf, "VS", font(90), GOLD, (W // 2, 20), "midtop", outline=6)
        text(surf, "ROUND %d" % self.vs_round, nfont(30, True), WHITE, (W // 2, 118), "midtop", 3)
        if self.final: text(surf, "WINNER TAKES THE LEGENDARY HARISSA", nfont(26, True), (255, 190, 90), (W // 2, 152), "midtop", 3)
        if self.time < 1200 or self.vs_state == "intro":
            a = 255 if self.vs_state == "intro" else int(255 * clamp((1200 - self.time) / 120, 0, 1))
            hs = pygame.Surface((W - 200, 52), pygame.SRCALPHA); rrect(hs, (0, 0, 0, int(a * .6)), hs.get_rect(), 14); surf.blit(hs, (100, H - 70))
            text(surf, HINT_MP, nfont(25, True), (255, 245, 210), (W // 2, H - 44), "center", 2, alpha=a)

    # -- boss death cinematic ---------------------------------------------------------------
    def begin_boss_cinematic(self):
        e = self.bd_pending; self.bd_pending = None; pl = self.player
        self.state = "bossdeath"
        self.bd = dict(t=0, acc=0.0, boss=e, landed=False, land_t=0, done_t=0, bars=0.0, name=e.name)
        self.projs = [p for p in self.projs if p.friendly]; self.hazards = [h for h in self.hazards if h.friendly]
        for en in self.enemies:
            if en is not e and en.state != "dead": en.die(self, 0)
        away = 1 if e.x >= pl.x else -1
        was_down = e.on_ground and e.t > 30                  # already lying on the floor (e.g. killed during the ultimate)
        if not was_down:                                     # launch the boss up and back for the slow-motion fall
            e.vx = away * 5.5; e.vy = -24; e.on_ground = False; e.y = min(e.y, GROUND - 2); e.t = 0
        e.state = "dead"; e.alpha = 255; e.face = -away; e.flash = 0
        if was_down: self.bd["landed"] = True; self.bd["land_t"] = 0
        for p in self.players: p.face = away; p.vx = 0
        self.stop = 0; self.slow = 0; self.presses = []
        audio.play("ko", 1.0)

    def bd_rate(self):
        bd = self.bd
        if bd["done_t"] > 0: return clamp(.3 + .7 * bd["done_t"] / 60.0, .3, 1.0)
        if not bd["landed"]: return .24
        return .3

    def bd_zoom(self):
        bd = self.bd
        if bd["done_t"] > 0: return 1.0
        z = 1.0 + .5 * ease(clamp(bd["t"] / 60.0, 0, 1))
        if bd["landed"]: z += .22 * ease(clamp((bd["t"] - bd["land_t"]) / 120.0, 0, 1))
        return z

    def _bd_boom(self, b, spread, ymax):
        self.fx.boom(random.choice(("boom_round", "boom_ground", "boom_big", "boom_mush")), b.x + random.uniform(-spread, spread),
                     b.y - random.uniform(10, ymax), random.uniform(1.0, 2.0), 20)
        self.fx.shake = max(self.fx.shake, 10); audio.play("boom", .5)

    def update_boss_cinematic(self):
        bd = self.bd; b = bd["boss"]; bd["t"] += 1; t = bd["t"]; fx = self.fx; self.presses = []; self.presses2 = []
        bd["bars"] = clamp(bd["bars"] + (.04 if bd["done_t"] == 0 else -.03), 0, 1)
        if audio.ok:                                                         # music fades out under the fall
            try: pygame.mixer.music.set_volume(settings["music"] * clamp(1 - t / 150.0, 0, 1))
            except Exception: pass
        if not bd["landed"] and ((b.on_ground and b.t > 6) or t > 420):    # the boss hits the ground
            if not b.on_ground: b.y = GROUND; b.on_ground = True; b.vy = 0
            bd["landed"] = True; bd["land_t"] = t
            fx.ring(b.x, GROUND - 10, 520, (255, 220, 140), 40, 16); fx.ring(b.x, GROUND - 10, 320, WHITE, 30, 10)
            fx.boom("boom_ground", b.x, GROUND - 70, 3.4, 18); fx.dust(b.x, GROUND, 22)
            fx.burst(b.x, GROUND - 60, 40, ((255, 255, 255), (255, 200, 90), (255, 120, 30)), 16, (5, 12), (30, 60))
            fx.shake = max(fx.shake, 32); fx.flash = .55; fx.flash_color = WHITE
            audio.play("slam", 1.0); audio.play("boom", .8)
        if not bd["landed"]:
            if t % 8 == 0: self._bd_boom(b, 55, max(60, b.hh * .7))
            b.flash = 2 if (t // 4) % 2 == 0 else 0
        else:
            L = t - bd["land_t"]
            if L < 150 and L % 14 == 0: self._bd_boom(b, 80, 90)
            if L == 70:
                fx.boom("boom_mush", b.x, b.y - 90, 3.0, 16); fx.shake = max(fx.shake, 20); fx.flash = max(fx.flash, .4); audio.play("boom", .9)
            b.flash = 2 if (L < 70 and (L // 5) % 2 == 0) else 0
            if L >= 150 and bd["done_t"] == 0:                              # dissolve into light
                p = clamp((L - 150) / 100.0, 0, 1); b.alpha = int(255 * (1 - p)); bd["p"] = p
                if p >= 1:
                    b.alpha = 0; bd["done_t"] = 1
                    fx.flash = 1.0; fx.flash_color = WHITE; fx.shake = max(fx.shake, 20)
                    fx.ring(b.x, GROUND - 10, 700, (255, 235, 170), 44, 18); fx.boom("nuke", b.x, GROUND - 250, 5.0, 14)
                    fx.burst(b.x, GROUND - 100, 60, ((255, 255, 255), (255, 225, 120), (150, 200, 255)), 16, (6, 14), (30, 60), -0.1)
                    audio.play("boom", 1.0)
        if bd["done_t"] > 0:
            bd["done_t"] += 1
            if bd["done_t"] > 75 or t > 900:                                 # cinematic over -> victory state
                self.bd = None; self.state = "victory"; self.end_t = 0; self.slow = 0; fx.zoom_kick = 0
                self.banner = ("VICTORY!", self.ch["name"], 120, 120)
                audio.cur = None; audio.music("victory.mp3", loop=False)
                return
        if self.stop > 0:
            self.stop -= 1; return
        bd["acc"] += self.bd_rate(); n = int(bd["acc"]); bd["acc"] -= n
        for _ in range(n): self._bd_tick()

    def _bd_tick(self):
        bd = self.bd; b = bd["boss"]; pl = self.player; fx = self.fx
        self.tick += 1; self.time += 1
        for p in self.players:
            p.invuln = max(p.invuln, 30)
            p.update(self, dict(left=False, right=False, up=False, down=False), [])
        for e in self.enemies: e.update(self)
        self.enemies = [e for e in self.enemies if e.boss or not (e.state == "dead" and e.alpha <= 0)]
        for p in self.projs: p.update(self)
        self.projs = [p for p in self.projs if not p.dead]
        for h in self.hazards: h.update(self)
        self.hazards = [h for h in self.hazards if not h.dead]
        for s in self.sched: s[0] -= 1
        for s in [s for s in self.sched if s[0] <= 0]: s[1]()
        self.sched = [s for s in self.sched if s[0] > 0]
        if not bd["landed"]:                                                # fire trail while he falls
            for _ in range(2):
                fx.parts.append(Particle(b.x + random.uniform(-45, 45), b.y - random.uniform(20, max(40, b.hh)), random.uniform(-1, 1), random.uniform(-2.5, 0),
                                         34, random.choice(((255, 200, 80), (255, 120, 30), (200, 200, 255))), random.uniform(6, 12), -0.02, True))
        elif bd.get("p", 0) > 0 and bd["done_t"] == 0:                      # body turns to rising sparks
            for _ in range(5):
                fx.parts.append(Particle(b.x + random.uniform(-b.hw * 2.2, b.hw * 2.2), b.y - random.uniform(5, 110), random.uniform(-1, 1), random.uniform(-4, -1.5),
                                         random.randint(40, 70), random.choice(((255, 235, 150), (255, 255, 255), (170, 210, 255))), random.uniform(5, 10), -0.03, True))
        fx.update(world=True, screen=False)

    def draw_cinematic(self, surf):
        bd = self.bd; k = ease(bd["bars"]); bh = int(135 * k)
        if bh > 0:
            pygame.draw.rect(surf, BLACK, (0, 0, W, bh)); pygame.draw.rect(surf, BLACK, (0, H - bh, W, bh))
        if bd["landed"] and bd["done_t"] == 0:
            a = int(255 * clamp((bd["t"] - bd["land_t"] - 40) / 30.0, 0, 1))
            if a > 0:
                text(surf, "%s DEFEATED" % bd["name"].upper(), font(78), GOLD, (W // 2, H - max(60, bh // 2)), "center", alpha=a, outline=5)

    def _camera(self):
        pl = self.player
        target = pl.x - W / 2 + pl.face * 120
        if self.boss and self.boss.state != "dead" and self.state == "wave":
            target = (pl.x + self.boss.x) / 2 - W / 2
        if self.bd: target = self.bd["boss"].x * .75 + pl.x * .25 - W / 2
        if self.player2:                                              # two players: follow the middle of the team
            al = [p for p in self.players if p.state != "dead"] or self.players
            mid = sum(p.x for p in al) / len(al); target = mid - W / 2
            if self.boss and self.boss.state != "dead" and self.state == "wave": target = (mid + self.boss.x) / 2 - W / 2
            if self.bd: target = self.bd["boss"].x * .75 + mid * .25 - W / 2
        target = clamp(target, 0, self.world_w - W)
        self.cam = lerp(self.cam, target, 0.09)

    # -- drawing ----------------------------------------------------------------------------
    def draw(self, surf):
        if not self.net: return self._draw_scene(surf)
        st = random.getstate()                                        # drawing must never disturb the shared random sequence
        try:
            self._draw_scene(surf); self.net_overlay(surf)
        finally:
            random.setstate(st)

    def _draw_scene(self, surf):
        cam = int(self.cam); w = self.world
        w.blit(self.bg, (-cam, 0))
        for dx, ds in self.decor:
            if -400 < dx - cam < W + 100: w.blit(ds, (int(dx - cam), GROUND + 24 - ds.get_height()))
        if self.vs and self.final:                                    # the LEGENDARY HARISSA floats over the arena
            draw_legend_can(w, self.world_w / 2 - cam, GROUND - 330 + math.sin(self.time * .05) * 14, self.time, 2.0)
        for h in self.hazards: h.draw(w, cam)
        for k in self.pickups: k.draw(w, cam)
        for e in sorted(self.enemies, key=lambda e: e.state != "dead"): e.draw(w, cam, self.tick)
        for p in self.projs: p.draw(w, cam)
        for p in sorted(self.players, key=lambda q: q.y): p.draw(w, cam)
        self.fx.draw_world(w, cam); self.fx.draw_texts(w, cam)
        sx = sy = 0
        if self.fx.shake:
            sx = int(random.uniform(-1, 1) * self.fx.shake); sy = int(random.uniform(-1, 1) * self.fx.shake)
        surf.fill((0, 0, 0))
        if self.zoom > 1.004:
            z = self.zoom; cw = int(W / z); chh = int(H / z); fxp, fyp = self.zoom_focus()
            x0 = int(clamp(fxp - cw / 2, 0, W - cw)); y0 = int(clamp(fyp - chh / 2, 0, H - chh))
            if self.zbuf is None: self.zbuf = pygame.Surface((W, H)).convert()
            pygame.transform.scale(w.subsurface((x0, y0, cw, chh)), (W, H), self.zbuf)
            surf.blit(self.zbuf, (sx, sy))
        else:
            surf.blit(w, (sx, sy))
        self.amb_draw(surf)
        surf.blit(self.vig, (0, 0))
        if self.grade: surf.blit(self.grade, (0, 0))
        if self.fx.flash > .02:
            f = pygame.Surface((W, H)); f.fill(self.fx.flash_color); f.set_alpha(int(255 * min(1, self.fx.flash))); surf.blit(f, (0, 0))
        if self.player.hp < self.player.maxhp * .25 and self.player.state != "dead":
            a = int(40 + 30 * math.sin(self.time * .15)); f = pygame.Surface((W, H), pygame.SRCALPHA)
            pygame.draw.rect(f, (255, 0, 0, a), (0, 0, W, H), 40); surf.blit(f, (0, 0))
        if self.ult: self.draw_ult_overlay(surf)
        if self.bd: self.draw_cinematic(surf)
        else: self.draw_hud(surf)
        self.draw_banner(surf)
        if self.paused: self.draw_pause(surf)
        if touch:
            touch.draw(surf)

    def draw_hud(self, surf):
        if self.vs: self.draw_vs_hud(surf); return
        self.draw_player_panel(surf, self.player, self.portrait, 0, 1)
        if self.player2: self.draw_player_panel(surf, self.player2, self.portrait2, 250, 2)
        self.draw_hud_common(surf)

    def draw_player_panel(self, surf, p, portrait, oy, pid):
        tmp = pygame.Surface((740, 260), pygame.SRCALPHA); self._panel_body(tmp, p, portrait, pid); surf.blit(tmp, (0, oy))

    def _panel_body(self, surf, p, portrait, pid):
        # player panel
        panel = pygame.Surface((680, 192), pygame.SRCALPHA); rrect(panel, (10, 10, 18, 190), panel.get_rect(), 22)
        rrect(panel, (255, 200, 80, 255), panel.get_rect(), 22, 3); surf.blit(panel, (24, 20))
        rrect(surf, (35, 28, 50), (40, 36, 124, 124), 16); rrect(surf, GOLD, (40, 36, 124, 124), 16, 3)
        surf.blit(portrait, (102 - portrait.get_width() // 2, 100 - portrait.get_height() // 2))
        text(surf, p.name, font(36), GOLD, (184, 32))
        bar(surf, (184, 78, 480, 34), p.hp / p.maxhp, (210, 45, 55) if p.hp > p.maxhp * .3 else (255, 70, 40), trail=p.hp_trail / p.maxhp)
        text(surf, "%d / %d" % (p.hp, p.maxhp), nfont(24, True), WHITE, (190 + 236, 95), "center", 2)
        ready = p.energy >= SPECIAL_COST
        col = (80, 170, 255) if not ready else (255 + int(0 * 1), 190 - int(40 * math.sin(self.time * .2)), 60)
        bar(surf, (184, 126, 380, 22), p.energy / 100, col)
        pygame.draw.line(surf, WHITE, (184 + 380 * SPECIAL_COST / 100, 124), (184 + 380 * SPECIAL_COST / 100, 150), 3)
        text(surf, ("SPECIAL [C]" if pid == 1 else "SPECIAL [/]") if ready else "ENERGY", nfont(22, True), GOLD if ready else (170, 200, 255), (574, 126))
        ur = p.ult_meter >= 100
        ucol = (255, int(clamp(190 - 50 * math.sin(self.time * .3), 0, 255)), 60) if ur else (190, 90, 255)
        bar(surf, (184, 160, 380, 16), p.ult_meter / 100, ucol, r=6)
        text(surf, ("ULTIMATE [R]" if pid == 1 else "ULTIMATE [ENTER]") if ur else "ULT %d%%" % int(p.ult_meter), nfont(20, True), GOLD if ur else (215, 170, 255), (574, 158))
        # cooldown pips for the heavy variants
        for i, (nm, lab) in enumerate((("PILLARS", "D+X"), ("PHOENIX", "U+X"), ("COMET", "DASH+X"), ("AIRHEAVY", "AIR X"))):
            cd = p.cds.get(nm, 0); mx = max(1, p.MV[nm].get("cd", 1)); fr = 1 - cd / mx
            bx = 30 + i * 108
            rrect(surf, (20, 18, 30), (bx, 222, 100, 20), 8)
            rrect(surf, (255, 190, 70) if fr >= 1 else (90, 80, 110), (bx + 2, 224, int(96 * fr), 16), 6)
            text(surf, lab, nfont(15, True), BLACK if fr >= 1 else WHITE, (bx + 50, 232), "center", 0)

    def draw_hud_common(self, surf):
        # top centre
        if self.wave >= 0 and self.state in ("wave", "clear", "intro", "victory"):
            alive = len([e for e in self.enemies if e.state != "dead"]) + len(self.queue)
            wv = self.waves[self.wave]
            lab = ("CH %d  " % self.ch["num"]) + (wv["title"] if not wv.get("boss") else wv["title"])
            if not (self.boss and self.boss.state != "dead"):
                text(surf, "%s    ENEMIES: %d" % (lab, alive), font(34), WHITE, (W // 2 + 40, 22), "midtop", outline=3)
        # boss bar
        b = self.boss
        if b and b.state != "dead" and self.state == "wave":
            bw = 1000; x = W // 2 - bw // 2 + 120
            text(surf, "%s  -  PHASE %d" % (b.name.upper(), b.phase()), font(38), (255, 90, 70), (x + bw // 2, 18), "midtop", outline=3)
            bar(surf, (x, 68, bw, 30), b.hp / b.maxhp, (200, 30, 120), trail=b.hp_trail / b.maxhp)
        # score
        text(surf, "SCORE  %07d" % self.score, font(40), WHITE, (W - 40, 24), "topright", outline=3)
        # combo
        if self.combo >= 2:
            pop = self.combo_pop; size = int(96 + 50 * pop)
            c = self.combo
            rank, rc = ("S", (255, 70, 90)) if c >= 28 else ("A", (255, 150, 40)) if c >= 18 else ("B", GOLD) if c >= 10 else ("C", (120, 220, 120)) if c >= 5 else ("D", (190, 190, 190))
            text(surf, str(c), font(size), rc, (W - 180, 150), "midright", outline=5)
            text(surf, "HITS", font(44), WHITE, (W - 50, 104), "topright", outline=4)
            text(surf, "RANK " + rank, font(36), rc, (W - 50, 160), "topright", outline=3)
            text(surf, "+%d%% DMG" % (min(c, 30) * 2), nfont(28, True), (255, 230, 150), (W - 50, 212), "topright", 2)
            frac = clamp(self.combo_t / 160, 0, 1)
            pygame.draw.rect(surf, (0, 0, 0), (W - 350, 252, 304, 16), border_radius=6)
            pygame.draw.rect(surf, rc, (W - 348, 254, 300 * frac, 12), border_radius=5)
        # hints
        if self.time < 900 and not self.ult and not (touch and touch.active):
            a = int(255 * clamp((900 - self.time) / 120, 0, 1))
            hs = pygame.Surface((W - 200, 52), pygame.SRCALPHA); rrect(hs, (0, 0, 0, int(a * .6)), hs.get_rect(), 14)
            surf.blit(hs, (100, H - 70))
            text(surf, HINT_MP if (self.player2 and not self.net) else "ARROWS move  SPACE jump (x2)  Z light x3  X fireball  DOWN+X pillars  UP+X phoenix  C special  SHIFT dash  R ULTIMATE  ESC move list",
                 nfont(25, True), (255, 245, 210), (W // 2, H - 44), "center", 2, alpha=a)

    def draw_banner(self, surf):
        t, sub, life, tot = self.banner
        if life > 0:
            self.banner = (t, sub, life - 1, tot)
            k = clamp((tot - life) / 14, 0, 1) * clamp(life / 20, 0, 1)
            sz = int(150 * (0.8 + 0.2 * k)) if len(t) < 14 else int(120 * (0.8 + 0.2 * k))
            col = (255, 70, 70) if "BOSS" in t else GOLD
            text(surf, t, font(sz), col, (W // 2, 330), "center", alpha=int(255 * k), outline=6)
            if sub: text(surf, sub, font(60), WHITE, (W // 2, 440), "center", alpha=int(255 * k), outline=4)

    def draw_pause(self, surf):
        d = pygame.Surface((W, H), pygame.SRCALPHA); d.fill((0, 0, 0, 175)); surf.blit(d, (0, 0))
        text(surf, "PAUSED", font(100), GOLD, (W // 2, 70), "center", outline=6)
        panel = pygame.Surface((1500, 640), pygame.SRCALPHA); rrect(panel, (20, 16, 30, 230), panel.get_rect(), 24); rrect(panel, GOLD, panel.get_rect(), 24, 3)
        surf.blit(panel, (W // 2 - 750, 170))
        text(surf, "MOVE LIST", font(40), (255, 160, 60), (W // 2, 182), "midtop")
        for i, (k, v) in enumerate(MOVE_HELP):
            y = 240 + i * 41
            text(surf, k, nfont(28, True), GOLD, (W // 2 - 700, y), shadow=2)
            text(surf, v, nfont(28), WHITE, (W // 2 - 420, y), shadow=2)
        for i, (r, lab) in enumerate(zip(self.pause_rects(), ("RESUME", "QUIT"))):
            sel = self.pause_sel == i
            rrect(surf, (255, 190, 60) if sel else (60, 50, 80), r, 18); rrect(surf, WHITE, r, 18, 3 if sel else 1)
            text(surf, lab, font(42), BLACK if sel else WHITE, r.center, "center", shadow=0)


# ==============================================================================================
#  SHARED UI
# ==============================================================================================
_hero_cache = {}
def hero_anim(char, scale):
    k = (char, scale)
    if k not in _hero_cache:
        if char == "john":
            a = make_anim("idle.png", scale, dirs=["sprite", "sprite/sprite", "images"])
            if a.n <= 1: a = make_anim("john_idle.png", scale)
        else:
            a = make_anim("jane_idle.png", scale)
        _hero_cache[k] = a
    return _hero_cache[k]


_img_cache = {}
def nimg(name, scale):
    k = (name, scale)
    if k not in _img_cache:
        s = img(name)
        _img_cache[k] = pygame.transform.scale(s, (int(s.get_width() * scale), int(s.get_height() * scale)))
    return _img_cache[k]


def button(surf, rect, label, selected, size=44):
    rrect(surf, (255, 190, 60) if selected else (55, 45, 75), rect, 18)
    rrect(surf, WHITE if selected else (150, 130, 190), rect, 18, 3 if selected else 2)
    text(surf, label, font(size), BLACK if selected else WHITE, rect.center, "center", shadow=0)


def panel(surf, rect, alpha=215, border=GOLD):
    p = pygame.Surface(rect.size, pygame.SRCALPHA)
    rrect(p, (18, 14, 28, alpha), p.get_rect(), 22); rrect(p, border, p.get_rect(), 22, 3)
    surf.blit(p, rect.topleft)


# ==============================================================================================
#  MENU / OPTIONS
# ==============================================================================================
class MenuScene(Scene):
    BW, BH, SP, Y0 = 340, 100, 115, 270

    def __init__(self, game):
        super().__init__(game)
        self.bg = bg_cover("menu_play.png"); self.panel = img("menu_bg.png")
        self.btn = [(img("play1.png"), img("play2.png")), (img("multiplayer1.png"), img("multiplayer2.png")),
                    (img("option1.png"), img("option2.png")), (img("exit1.png"), img("exit2.png"))]
        dim = pygame.Surface((W, H)); dim.fill((0, 0, 0)); dim.set_alpha(120); self.bg = self.bg.copy(); self.bg.blit(dim, (0, 0))
        self.sel = 0; self.t = 0; self.toast = ""; self.toast_t = 0; game.mp = None
        self.fp = [[random.uniform(0, W), random.uniform(0, H), random.uniform(.5, 2), random.uniform(2, 5)] for _ in range(36)]
        audio.music("menu_bg_music.mp3")

    def rect(self, i): return pygame.Rect(W // 2 - self.BW // 2, self.Y0 + i * self.SP, self.BW, self.BH)

    def pick(self, i):
        audio.play("confirm")
        if i == 0: self.game.mp = None; self.game.go(AvatarScene(self.game))
        elif i == 1:
            try:
                from online_scenes import PlayModeScene
                self.game.go(PlayModeScene(self.game))
            except Exception:
                traceback.print_exc(); self.game.go(MPCharScene(self.game))        # online module missing -> local 2-player only
        elif i == 2: self.game.go(OptionsScene(self.game))
        else: pygame.quit(); sys.exit()

    def event(self, e):
        if e.type == pygame.MOUSEMOTION:
            for i in range(4):
                if self.rect(i).collidepoint(e.pos) and self.sel != i: self.sel = i; audio.play("hover", .5)
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            for i in range(4):
                if self.rect(i).collidepoint(e.pos): self.pick(i)
        elif e.type == pygame.KEYDOWN:
            if e.key in (pygame.K_UP, pygame.K_w): self.sel = (self.sel - 1) % 4; audio.play("hover", .5)
            elif e.key in (pygame.K_DOWN, pygame.K_s): self.sel = (self.sel + 1) % 4; audio.play("hover", .5)
            elif e.key in (pygame.K_RETURN, pygame.K_SPACE): self.pick(self.sel)

    def update(self):
        self.t += 1; self.toast_t = max(0, self.toast_t - 1)
        for p in self.fp:
            p[1] -= p[2]; p[0] += math.sin(self.t * .02 + p[3]) * .6
            if p[1] < -10: p[1] = H + 10; p[0] = random.uniform(0, W)

    def draw(self, surf):
        surf.blit(self.bg, (0, 0))
        for p in self.fp:
            pygame.draw.circle(surf, (255, 150 + int(60 * math.sin(self.t * .05 + p[3])), 40), (int(p[0]), int(p[1])), int(p[3]))
        surf.blit(self.panel, (W // 2 - self.panel.get_width() // 2, 0))
        for i, (n, s) in enumerate(self.btn):
            im = s if i == self.sel else n
            r = self.rect(i)
            if i == self.sel:
                im = pygame.transform.smoothscale(im, (int(im.get_width() * (1.05 + .02 * math.sin(self.t * .15))), int(im.get_height() * (1.05 + .02 * math.sin(self.t * .15)))))
            surf.blit(im, im.get_rect(center=r.center))
        text(surf, "ARROWS / MOUSE + ENTER", nfont(26, True), (255, 235, 190), (W // 2, H - 40), "center", 2)
        if self.toast_t: text(surf, self.toast, font(44), GOLD, (W // 2, 880), "center", alpha=min(255, self.toast_t * 8), outline=4)


class OptionsScene(Scene):
    def __init__(self, game):
        super().__init__(game); self.bgimg = bg_cover("menu_play.png"); self.sel = 0; self.t = 0
        self.rows = ["MUSIC", "EFFECTS", "FULLSCREEN", "BACK"]

    def rrect_row(self, i): return pygame.Rect(W // 2 - 500, 330 + i * 110, 1000, 84)

    def adjust(self, i, d):
        if i == 0: settings["music"] = round(clamp(settings["music"] + d * .1, 0, 1), 2); audio.refresh()
        elif i == 1: settings["sfx"] = round(clamp(settings["sfx"] + d * .1, 0, 1), 2); audio.play("hit")
        elif i == 2 and d: self.game.toggle_fullscreen()

    def event(self, e):
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE: self.back()
            elif e.key in (pygame.K_UP, pygame.K_w): self.sel = (self.sel - 1) % 4; audio.play("hover", .5)
            elif e.key in (pygame.K_DOWN, pygame.K_s): self.sel = (self.sel + 1) % 4; audio.play("hover", .5)
            elif e.key in (pygame.K_LEFT, pygame.K_a): self.adjust(self.sel, -1)
            elif e.key in (pygame.K_RIGHT, pygame.K_d): self.adjust(self.sel, 1)
            elif e.key in (pygame.K_RETURN, pygame.K_SPACE):
                if self.sel == 2: self.adjust(2, 1)
                elif self.sel == 3: self.back()
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            for i in range(4):
                r = self.rrect_row(i)
                if r.collidepoint(e.pos):
                    self.sel = i
                    if i in (0, 1):
                        v = clamp((e.pos[0] - (r.x + 330)) / 600, 0, 1); settings["music" if i == 0 else "sfx"] = round(v, 2); audio.refresh()
                    elif i == 2: self.adjust(2, 1)
                    else: self.back()

    def back(self):
        save_settings(); audio.play("confirm"); self.game.go(MenuScene(self.game))

    def draw(self, surf):
        surf.blit(self.bgimg, (0, 0)); d = pygame.Surface((W, H), pygame.SRCALPHA); d.fill((0, 0, 0, 170)); surf.blit(d, (0, 0))
        text(surf, "OPTIONS", font(110), GOLD, (W // 2, 120), "center", outline=6)
        for i, lab in enumerate(self.rows):
            r = self.rrect_row(i); sel = i == self.sel
            panel(surf, r, 230 if sel else 150, GOLD if sel else (110, 100, 140))
            text(surf, lab, font(40), GOLD if sel else WHITE, (r.x + 34, r.centery), "midleft")
            if i in (0, 1):
                v = settings["music" if i == 0 else "sfx"]
                pygame.draw.rect(surf, (50, 45, 65), (r.x + 330, r.centery - 8, 600, 16), border_radius=8)
                pygame.draw.rect(surf, ORANGE, (r.x + 330, r.centery - 8, 600 * v, 16), border_radius=8)
                pygame.draw.circle(surf, WHITE, (int(r.x + 330 + 600 * v), r.centery), 18)
                text(surf, "%d%%" % int(v * 100), nfont(30, True), WHITE, (r.right - 30, r.centery), "midright")
            elif i == 2:
                text(surf, "ON" if settings["fullscreen"] else "OFF", font(40), GREEN if settings["fullscreen"] else GREY, (r.x + 330, r.centery), "midleft")
        text(surf, "F11 also toggles fullscreen anywhere", nfont(28), (210, 200, 230), (W // 2, 800), "center", 2)
        text(surf, "CONTROLS:  Arrows | SPACE jump x2 | Z light | X heavy | C special | SHIFT dash | R ULTIMATE | UP/DOWN+X combos", nfont(28, True), WHITE, (W // 2, 880), "center", 2)


# ==============================================================================================
#  AVATAR SELECT
# ==============================================================================================
class AvatarScene(Scene):
    def __init__(self, game):
        super().__init__(game); self.bg = bg_cover("bgcsp.png"); self.sel = 0; self.t = 0; self.go_t = 0
        self.chars = ["john", "jane"]; audio.music("csm.mp3")
        self.xs = [W // 2 - 400, W // 2 + 400]; self.names = ["JOHN", "JANE"]
        self.info = {"john": ["HP 300  -  Power +10%", "Harissa fire palms & fireballs", "Special: HARISSA NOVA"],
                     "jane": ["Speed +11%  -  HP 240", "Sword combos & light burst", "Special: SOLAR BEAM"]}

    def choose(self, i):
        if self.go_t: return
        self.sel = i; self.go_t = 1; audio.play("special", .8); self.game.char = self.chars[i]; self.game.mp = None

    def event(self, e):
        if self.go_t: return
        if e.type == pygame.KEYDOWN:
            if e.key in (pygame.K_LEFT, pygame.K_a): self.sel = 0; audio.play("hover", .6)
            elif e.key in (pygame.K_RIGHT, pygame.K_d): self.sel = 1; audio.play("hover", .6)
            elif e.key in (pygame.K_RETURN, pygame.K_SPACE): self.choose(self.sel)
            elif e.key == pygame.K_ESCAPE: self.game.go(MenuScene(self.game))
        elif e.type == pygame.MOUSEMOTION:
            for i, x in enumerate(self.xs):
                if abs(e.pos[0] - x) < 260 and 250 < e.pos[1] < 900 and self.sel != i: self.sel = i; audio.play("hover", .6)
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            for i, x in enumerate(self.xs):
                if abs(e.pos[0] - x) < 260 and 250 < e.pos[1] < 900: self.choose(i)

    def update(self):
        self.t += 1
        if self.go_t:
            self.go_t += 1
            if self.go_t == 70: self.game.after_avatar()

    def draw(self, surf):
        surf.blit(self.bg, (0, 0)); d = pygame.Surface((W, H), pygame.SRCALPHA); d.fill((0, 0, 0, 110)); surf.blit(d, (0, 0))
        text(surf, "CHOOSE YOUR HERO", font(100), GOLD, (W // 2, 70), "center", outline=6)
        for i, c in enumerate(self.chars):
            x = self.xs[i]; sel = i == self.sel; an = hero_anim(c, 7.0)
            pygame.draw.ellipse(surf, (0, 0, 0), (x - 230, 820, 460, 70));
            g = pygame.Surface((520, 100), pygame.SRCALPHA)
            pygame.draw.ellipse(g, (255, 190, 60, 150 if sel else 40), g.get_rect()); surf.blit(g, (x - 260, 810))
            bob = math.sin(self.t * .08) * 4 if sel else 0
            if self.go_t and sel: bob -= min(40, self.go_t * 2)
            an.draw(surf, int(self.t * 10 / FPS) % an.n, x, 850 + bob, 0, False, alpha=255 if sel else 130)
            text(surf, self.names[i], font(70 if sel else 54), GOLD if sel else GREY, (x, 190), "center", outline=4)
            if sel:
                for j, line in enumerate(self.info[c]): text(surf, line, nfont(30, True), WHITE, (x, 905 + j * 36), "midtop", 2)
                ar = 160 + math.sin(self.t * .15) * 10
                pygame.draw.polygon(surf, GOLD, [(x - 24, ar + 20), (x + 24, ar + 20), (x, ar + 52)])
        text(surf, "LEFT / RIGHT to pick   -   ENTER or CLICK to confirm", nfont(30, True), WHITE, (W // 2, H - 36), "center", 3)


# ==============================================================================================
#  DIALOGUE
# ==============================================================================================
class Actor:
    def __init__(self, key, x, feet, anim=None, surf=None, flip=False, floaty=False):
        self.key = key; self.x = x; self.feet = feet; self.anim = anim; self.surf = surf; self.flip = flip; self.floaty = floaty


class DialogueScene(Scene):
    def __init__(self, game, bg, actors, lines, on_done, music=None, overlay=0):
        super().__init__(game); self.bg = bg_cover(bg); self.actors = actors; self.lines = lines; self.i = 0; self.chars = 0.0
        self.on_done = on_done; self.t = 0; self.done = False; self.overlay = overlay
        if music: audio.music(music)

    def cur(self): return self.lines[self.i]

    def advance(self):
        if self.done: return
        txt = self.cur()[2]
        if self.chars < len(txt): self.chars = len(txt); return
        audio.play("tick", .5); self.i += 1; self.chars = 0
        if self.i >= len(self.lines): self.done = True; self.on_done()

    def event(self, e):
        if e.type == pygame.KEYDOWN:
            if e.key in (pygame.K_SPACE, pygame.K_RETURN, pygame.K_z): self.advance()
            elif e.key == pygame.K_TAB and not self.done: self.done = True; self.on_done()
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1: self.advance()

    def update(self):
        self.t += 1
        if not self.done:
            txt = self.cur()[2]
            if self.chars < len(txt):
                prev = int(self.chars); self.chars += 1.3
                if int(self.chars) != prev and int(self.chars) % 3 == 0 and txt[min(int(self.chars), len(txt) - 1)] != " ": audio.play("tick", .12)

    def draw(self, surf):
        surf.blit(self.bg, (0, 0))
        if self.overlay: d = pygame.Surface((W, H), pygame.SRCALPHA); d.fill((0, 0, 0, self.overlay)); surf.blit(d, (0, 0))
        key, name, txt = self.cur() if not self.done else (None, "", "")
        for a in self.actors:
            speaking = a.key == key
            bob = math.sin(self.t * .12) * 8 if a.floaty else 0
            if speaking: bob -= 6 + math.sin(self.t * .25) * 3
            if a.anim:
                a.anim.draw(surf, int(self.t * 10 / FPS) % a.anim.n, a.x, a.feet + bob, 0, a.flip)
            elif a.surf:
                s = pygame.transform.flip(a.surf, True, False) if a.flip else a.surf
                if a.floaty:
                    g = pygame.Surface((s.get_width() + 80, s.get_height() + 80), pygame.SRCALPHA)
                    pygame.draw.ellipse(g, (255, 210, 120, 50 + int(25 * math.sin(self.t * .1))), g.get_rect()); surf.blit(g, g.get_rect(center=(a.x, a.feet - s.get_height() // 2 + bob)))
                surf.blit(s, s.get_rect(midbottom=(a.x, a.feet + bob)))
        box = pygame.Rect(70, H - 290, W - 140, 230)
        panel(surf, box, 225)
        if name:
            tag = pygame.Rect(box.x + 40, box.y - 30, 360, 56); rrect(surf, GOLD, tag, 16); rrect(surf, BLACK, tag, 16, 3)
            text(surf, name, font(38), BLACK, tag.center, "center", shadow=0)
        shown = txt[:int(self.chars)]
        f = nfont(40, key is not None); col = WHITE if key is not None else (255, 225, 160)
        for j, line in enumerate(wrap(shown, f, box.w - 100)[:4]):
            text(surf, line, f, col, (box.x + 50, box.y + 44 + j * 52), shadow=2)
        if self.chars >= len(txt) and (self.t // 25) % 2 == 0 and not self.done:
            text(surf, "SPACE", nfont(26, True), GOLD, (box.right - 40, box.bottom - 24), "bottomright", 2)
        text(surf, "TAB: skip", nfont(22), (200, 200, 200), (W - 30, 20), "topright", 2)


# ==============================================================================================
#  GAME OVER / VICTORY
# ==============================================================================================
class EndScene(Scene):
    def make_buttons(self, labels):
        self.labels = labels; self.sel = 0
        n = len(labels); self.rects = [pygame.Rect(W // 2 - (n * 460 - 20) // 2 + i * 460, 860, 440, 90) for i in range(n)]

    def event(self, e):
        if e.type == pygame.KEYDOWN:
            if e.key in (pygame.K_LEFT, pygame.K_a, pygame.K_UP): self.sel = (self.sel - 1) % len(self.labels); audio.play("hover", .5)
            elif e.key in (pygame.K_RIGHT, pygame.K_d, pygame.K_DOWN): self.sel = (self.sel + 1) % len(self.labels); audio.play("hover", .5)
            elif e.key in (pygame.K_RETURN, pygame.K_SPACE): self.pick(self.sel)
        elif e.type == pygame.MOUSEMOTION:
            for i, r in enumerate(self.rects):
                if r.collidepoint(e.pos) and self.sel != i: self.sel = i; audio.play("hover", .5)
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            for i, r in enumerate(self.rects):
                if r.collidepoint(e.pos): self.pick(i)

    def draw_buttons(self, surf):
        for i, (r, lab) in enumerate(zip(self.rects, self.labels)): button(surf, r, lab, i == self.sel)


def ch_cover(ch):
    k = ("chcover", ch["key"])
    if k not in _bg_cache:
        _bg_cache[k] = cover(img(ch["bg_file"], dirs=["maps"])) if ch.get("bg_file") else bg_cover("tataouine_bg.png")
    return _bg_cache[k]


def rank_for(pts):
    return "S" if pts > 30000 else "A" if pts > 22000 else "B" if pts > 15000 else "C"

RANK_COL = {"S": (255, 70, 90), "A": (255, 150, 40), "B": GOLD, "C": (120, 220, 120)}


class GameOverScene(EndScene):
    def __init__(self, game, kind, ref):
        super().__init__(game); self.kind = kind; self.ref = ref; self.bg = bg_cover("tataouine_bg.png"); self.t = 0
        self.make_buttons(["TRY AGAIN", "MAIN MENU"]); audio.music("gameover.mp3")

    def pick(self, i):
        audio.play("confirm")
        if i == 1: self.game.go(MenuScene(self.game))
        else: self.game.start_fight(self.ref.ci)

    def update(self): self.t += 1

    def draw(self, surf):
        surf.blit(self.bg, (0, 0)); d = pygame.Surface((W, H), pygame.SRCALPHA); d.fill((0, 0, 0, 150)); surf.blit(d, (0, 0))
        k = clamp(self.t / 25, 0, 1); r = self.ref
        text(surf, "YOU LOST", font(int(190 * (.7 + .3 * k))), (230, 60, 60), (W // 2, 330), "center", alpha=int(255 * k), outline=8)
        text(surf, "Chapter %d: %s" % (r.ch["num"], r.ch["name"]), font(52), WHITE, (W // 2, 500), "center", outline=4)
        text(surf, "Score %d      Best combo %d      Enemies beaten %d" % (r.score, r.max_combo, r.kills), nfont(40, True), GOLD, (W // 2, 620), "center", 3)
        self.draw_buttons(surf)


class ChapterClearScene(EndScene):
    def __init__(self, game, ref):
        super().__init__(game); self.ref = ref; self.ch = ref.ch; self.bg = ch_cover(self.ch); self.t = 0
        self.make_buttons(["NEXT CHAPTER", "MAIN MENU"]); audio.music("victory.mp3", loop=False)
        secs = ref.time / 60; hp = ref.player.hp / ref.player.maxhp
        self.pts = ref.score + int(hp * 3000) + max(0, int((420 - secs) * 15)) + ref.max_combo * 120
        self.secs = secs; self.rank = rank_for(self.pts); self.nxt = CHAPTERS[ref.ci + 1]
        self.conf = [[random.uniform(0, W), random.uniform(-H, 0), random.uniform(3, 8), random.choice([(255, 200, 60), (255, 90, 60), (90, 200, 255), (255, 255, 255)])] for _ in range(90)]

    def pick(self, i):
        audio.play("confirm")
        if i == 1: self.game.go(MenuScene(self.game))
        else: self.game.story_chapter(self.ref.ci + 1)

    def update(self):
        self.t += 1
        for c in self.conf:
            c[1] += c[2]; c[0] += math.sin(c[1] * .02) * 2
            if c[1] > H: c[1] = -10; c[0] = random.uniform(0, W)

    def draw(self, surf):
        surf.blit(self.bg, (0, 0)); d = pygame.Surface((W, H), pygame.SRCALPHA); d.fill((0, 0, 0, 140)); surf.blit(d, (0, 0))
        for c in self.conf: pygame.draw.rect(surf, c[3], (int(c[0]), int(c[1]), 10, 16))
        k = clamp(self.t / 25, 0, 1); r = self.ref
        text(surf, "CHAPTER %d CLEARED!" % self.ch["num"], font(int(150 * (.7 + .3 * k))), GOLD, (W // 2, 170), "center", alpha=int(255 * k), outline=8)
        text(surf, self.ch["name"], font(54), WHITE, (W // 2, 290), "center", outline=4)
        y = 360
        for lab, val in (("Score", r.score), ("Enemies beaten", r.kills), ("Best combo", r.max_combo),
                         ("Time", "%d:%02d" % (self.secs // 60, self.secs % 60)), ("Health left", "%d%%" % int(100 * r.player.hp / r.player.maxhp))):
            text(surf, lab, nfont(40, True), (230, 220, 200), (W // 2 - 360, y), "topleft", 3)
            text(surf, str(val), nfont(40, True), WHITE, (W // 2 + 60, y), "topright", 3); y += 56
        text(surf, self.rank, font(240), RANK_COL[self.rank], (W // 2 + 380, 470), "center", alpha=int(255 * k), outline=9)
        text(surf, "REWARD:  +5%% damage and +10 starting energy for the next chapters", nfont(36, True), (255, 240, 170), (W // 2, 680), "center", 3)
        text(surf, "NEXT:  Chapter %d  -  %s" % (self.nxt["num"], self.nxt["name"]), font(46), (255, 150, 70), (W // 2, 760), "center", outline=3)
        self.draw_buttons(surf)


class ChapterSelectScene(Scene):
    CW, CH_, GAP = 330, 520, 24

    def __init__(self, game):
        super().__init__(game); self.bg = bg_cover("menu_play.png"); self.t = 0
        self.unlocked = clamp(settings.get("unlocked", 1), 1, len(CHAPTERS)); self.sel = self.unlocked - 1
        audio.music("csm.mp3")

    def rect(self, i):
        tot = len(CHAPTERS) * self.CW + (len(CHAPTERS) - 1) * self.GAP
        return pygame.Rect(W // 2 - tot // 2 + i * (self.CW + self.GAP), 300, self.CW, self.CH_)

    def pick(self, i):
        if i >= self.unlocked: audio.play("false"); return
        audio.play("confirm"); g = self.game
        if i == 0: g.story_airport()
        else: g.blessing = 1 + 0.05 * i; g.start_energy = 10 * i; g.total_score = 0; g.story_chapter(i)

    def event(self, e):
        if e.type == pygame.KEYDOWN:
            if e.key in (pygame.K_LEFT, pygame.K_a): self.sel = (self.sel - 1) % len(CHAPTERS); audio.play("hover", .5)
            elif e.key in (pygame.K_RIGHT, pygame.K_d): self.sel = (self.sel + 1) % len(CHAPTERS); audio.play("hover", .5)
            elif e.key in (pygame.K_RETURN, pygame.K_SPACE): self.pick(self.sel)
            elif e.key == pygame.K_ESCAPE: self.game.go(MenuScene(self.game))
        elif e.type == pygame.MOUSEMOTION:
            for i in range(len(CHAPTERS)):
                if self.rect(i).collidepoint(e.pos) and self.sel != i: self.sel = i; audio.play("hover", .5)
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            for i in range(len(CHAPTERS)):
                if self.rect(i).collidepoint(e.pos): self.sel = i; self.pick(i)

    def update(self): self.t += 1

    def draw(self, surf):
        surf.blit(self.bg, (0, 0)); d = pygame.Surface((W, H), pygame.SRCALPHA); d.fill((0, 0, 0, 160)); surf.blit(d, (0, 0))
        text(surf, "SELECT CHAPTER", font(100), GOLD, (W // 2, 120), "center", outline=6)
        for i, ch in enumerate(CHAPTERS):
            r = self.rect(i); sel = i == self.sel; lock = i >= self.unlocked
            if sel: r = r.inflate(24, 24).move(0, -12)
            panel(surf, r, 235 if sel else 170, GOLD if sel else (110, 100, 140))
            th = ch_cover(ch); pw = r.w - 30; ph = int(pw * 0.62)
            thumb = pygame.transform.smoothscale(th, (pw, ph))
            if lock: thumb.fill((20, 20, 20), special_flags=pygame.BLEND_RGB_MULT)
            surf.blit(thumb, (r.x + 15, r.y + 15))
            text(surf, "CHAPTER %d" % ch["num"], font(36), GOLD if not lock else GREY, (r.centerx, r.y + ph + 40), "midtop", outline=3)
            yy = r.y + ph + 90
            for ln in wrap(ch["name"], font(30), r.w - 30)[:2]:
                text(surf, ln, font(30), WHITE if not lock else GREY, (r.centerx, yy), "midtop", 2); yy += 36
            for ln in wrap(ch["sub"], nfont(24), r.w - 40)[:3]:
                text(surf, ln, nfont(24), (220, 210, 190) if not lock else (110, 110, 110), (r.centerx, yy + 6), "midtop", 2); yy += 28
            if lock: text(surf, "LOCKED", font(54), (230, 70, 70), (r.centerx, r.y + ph // 2 + 15), "center", outline=4)
        text(surf, "LEFT / RIGHT to pick   -   ENTER or CLICK to start   -   ESC back", nfont(30, True), WHITE, (W // 2, H - 60), "center", 3)


class VictoryScene(EndScene):
    def __init__(self, game, ref):
        super().__init__(game); self.ref = ref; self.bg = bg_cover("carthage_bg.png"); self.t = 0
        self.make_buttons(["PLAY AGAIN", "MAIN MENU"]); audio.music("victory.mp3", loop=False)
        secs = ref.time / 60; hp = ref.player.hp / ref.player.maxhp
        pts = game.total_score + int(hp * 3000) + ref.max_combo * 120
        self.total = pts; self.secs = secs
        self.rank = "S" if pts > 110000 else "A" if pts > 80000 else "B" if pts > 50000 else "C"
        self.new_best = pts > settings.get("best", 0)
        if self.new_best: settings["best"] = pts; save_settings()
        self.conf = [[random.uniform(0, W), random.uniform(-H, 0), random.uniform(3, 8), random.choice([(255, 200, 60), (255, 90, 60), (90, 200, 255), (255, 255, 255)])] for _ in range(120)]

    def pick(self, i):
        audio.play("confirm")
        if i == 1: self.game.go(MenuScene(self.game))
        else: self.game.go(MPCharScene(self.game) if self.game.mp else AvatarScene(self.game))

    def update(self):
        self.t += 1
        for c in self.conf:
            c[1] += c[2]; c[0] += math.sin(c[1] * .02) * 2
            if c[1] > H: c[1] = -10; c[0] = random.uniform(0, W)

    def draw(self, surf):
        surf.blit(self.bg, (0, 0)); d = pygame.Surface((W, H), pygame.SRCALPHA); d.fill((0, 0, 0, 100)); surf.blit(d, (0, 0))
        for c in self.conf: pygame.draw.rect(surf, c[3], (int(c[0]), int(c[1]), 10, 16))
        k = clamp(self.t / 25, 0, 1)
        text(surf, "VICTORY!", font(int(200 * (.7 + .3 * k))), GOLD, (W // 2, 190), "center", alpha=int(255 * k), outline=8)
        text(surf, "Dark Anakin is defeated - the harissa is saved!", font(52), WHITE, (W // 2, 340), "center", outline=4)
        r = self.ref; y = 440
        for lab, val in (("Total score", self.game.total_score), ("Chapters cleared", "5 / 5"), ("Best combo (last chapter)", r.max_combo),
                         ("Health left", "%d%%" % int(100 * r.player.hp / r.player.maxhp))):
            text(surf, lab, nfont(40, True), (230, 220, 200), (W // 2 - 360, y), "topleft", 3)
            text(surf, str(val), nfont(40, True), WHITE, (W // 2 + 160, y), "topright", 3); y += 56
        text(surf, self.rank, font(250), RANK_COL[self.rank], (W // 2 + 420, 520), "center", alpha=int(255 * k), outline=9)
        text(surf, "FINAL %d" % self.total + ("   NEW BEST!" if self.new_best else "   Best %d" % settings["best"]), font(50), GOLD, (W // 2, 760), "center", outline=4)
        self.draw_buttons(surf)


# ==============================================================================================
#  MULTIPLAYER  (controls, legendary harissa art, scenes)
# ==============================================================================================
VS_DMG = 0.9
KEYS_P1 = {pygame.K_z: "light", pygame.K_x: "heavy", pygame.K_c: "special", pygame.K_SPACE: "jump", pygame.K_LSHIFT: "dash",
           pygame.K_v: "dash", pygame.K_r: "ult", pygame.K_q: "ult"}
KEYS_P2 = {pygame.K_COMMA: "light", pygame.K_PERIOD: "heavy", pygame.K_SLASH: "special", pygame.K_RCTRL: "jump", pygame.K_RALT: "jump",
           pygame.K_RSHIFT: "dash", pygame.K_RETURN: "ult", pygame.K_KP1: "light", pygame.K_KP2: "heavy", pygame.K_KP3: "special",
           pygame.K_KP0: "jump", pygame.K_KP_ENTER: "ult"}
P_COL = {1: (90, 170, 255), 2: (255, 90, 90)}
HINT_MP = "P1: WASD move - SPACE jump - Z / X / C attacks - V dash - R ult        P2: ARROWS move - R-CTRL jump - , . / attacks - R-SHIFT dash - ENTER ult"

_leg_cache = {}
def legend_frames(name, n, cw, ch, scale):
    k = (name, scale)
    if k not in _leg_cache:
        s = img(name)
        if s.get_width() < n * cw or s.get_height() < ch:
            out = [s]                                               # asset missing: keep the game alive
        else:
            out = []
            for i in range(n):
                f = s.subsurface((i * cw, 0, cw, ch)).copy()
                if scale != 1: f = pygame.transform.smoothscale(f, (int(cw * scale), int(ch * scale)))
                out.append(f)
        _leg_cache[k] = out
    return _leg_cache[k]


_disc_cache = {}
def glow_disc(r, col, power=1.8):
    r = max(8, int(r) // 8 * 8); k = (r, col)
    if k not in _disc_cache: _disc_cache[k] = _radial(r, col, power)
    return _disc_cache[k]


def draw_legend_can(surf, cx, cy, t, scale=2.4, halo=1.0):
    """the LEGENDARY HARISSA can (Jouda power-up sheet): spinning can inside a pulsing additive fire halo"""
    pul = 1 + .12 * math.sin(t * .09)
    g = glow_disc(210 * scale / 2.4 * pul * halo, (255, 110, 20), 1.7)
    surf.blit(g, (int(cx - g.get_width() / 2), int(cy - g.get_height() / 2)), special_flags=pygame.BLEND_RGB_ADD)
    sp = legend_frames("legend_spin.png", 8, 150, 136, scale)
    f = sp[int(t * .22) % len(sp)]
    surf.blit(f, f.get_rect(center=(int(cx), int(cy))))


class MPCharScene(Scene):
    """both players pick a hero (they can't pick the same one)"""
    K = (((pygame.K_a,), (pygame.K_d,), (pygame.K_z, pygame.K_SPACE, pygame.K_v)),
         ((pygame.K_LEFT,), (pygame.K_RIGHT,), (pygame.K_COMMA, pygame.K_PERIOD, pygame.K_SLASH, pygame.K_RETURN)))

    def __init__(self, game):
        super().__init__(game); game.mp = None
        self.bg = bg_cover("bgcsp.png"); self.t = 0; self.go_t = 0; audio.music("csm.mp3")
        self.chars = ["john", "jane"]; self.xs = [W // 2 - 400, W // 2 + 400]; self.names = ["JOHN", "JANE"]
        self.sel = [0, 1]; self.lock = [None, None]

    def event(self, e):
        if self.go_t or e.type != pygame.KEYDOWN: return
        k = e.key
        if k == pygame.K_ESCAPE: self.game.go(MenuScene(self.game)); return
        for p in (0, 1):
            Ls, Rs, OKs = self.K[p]
            if k in Ls or k in Rs:
                self.lock[p] = None; self.sel[p] = 0 if k in Ls else 1; audio.play("hover", .6)
            elif k in OKs and self.lock[p] is None:
                if self.lock[1 - p] == self.sel[p]: audio.play("false"); continue
                self.lock[p] = self.sel[p]; audio.play("special", .7)
                if self.lock[1 - p] is None: self.sel[1 - p] = 1 - self.lock[p]

    def update(self):
        self.t += 1
        if self.lock[0] is not None and self.lock[1] is not None:
            self.go_t += 1
            if self.go_t == 60:
                g = self.game; c = [self.chars[self.lock[0]], self.chars[self.lock[1]]]
                g.mp = dict(chars=tuple(c), story=False, vs=False, final=False, ci=0); g.char = c[0]
                g.mp_mode_menu()
        else: self.go_t = 0

    def draw(self, surf):
        surf.blit(self.bg, (0, 0)); d = pygame.Surface((W, H), pygame.SRCALPHA); d.fill((0, 0, 0, 120)); surf.blit(d, (0, 0))
        text(surf, "2 PLAYERS  -  CHOOSE YOUR HEROES", font(90), GOLD, (W // 2, 60), "center", outline=6)
        for i, c in enumerate(self.chars):
            x = self.xs[i]; on = i in self.sel or i in self.lock; an = hero_anim(c, 7.0)
            pygame.draw.ellipse(surf, (0, 0, 0), (x - 230, 820, 460, 70))
            g = pygame.Surface((520, 100), pygame.SRCALPHA); pygame.draw.ellipse(g, (255, 190, 60, 150 if on else 40), g.get_rect()); surf.blit(g, (x - 260, 810))
            bob = math.sin(self.t * .08) * 4 if on else 0
            an.draw(surf, int(self.t * 10 / FPS) % an.n, x, 850 + bob, 0, False, alpha=255 if on else 130)
            text(surf, self.names[i], font(70 if on else 54), GOLD if on else GREY, (x, 190), "center", outline=4)
            hs = [p for p in (0, 1) if self.sel[p] == i]
            for n, p in enumerate(hs):
                ox = (n - (len(hs) - 1) / 2) * 190; col = P_COL[p + 1]; ar = 262 + math.sin(self.t * .15) * 8
                locked = self.lock[p] == i
                rrect(surf, col, (x + ox - 70, ar - 62, 140, 52), 14); rrect(surf, WHITE if locked else BLACK, (x + ox - 70, ar - 62, 140, 52), 14, 3)
                text(surf, "P%d%s" % (p + 1, " OK" if locked else ""), font(36), BLACK, (x + ox, ar - 36), "center", shadow=0)
                pygame.draw.polygon(surf, col, [(x + ox - 22, ar - 6), (x + ox + 22, ar - 6), (x + ox, ar + 24)])
        text(surf, "P1:  A / D  move    Z or SPACE  confirm", nfont(30, True), P_COL[1], (W // 2 - 20, H - 80), "midright", 3)
        text(surf, "P2:  LEFT / RIGHT  move    , or ENTER  confirm", nfont(30, True), P_COL[2], (W // 2 + 20, H - 80), "midleft", 3)
        text(surf, "ESC  back", nfont(26, True), WHITE, (W // 2, H - 36), "center", 3)


class MPMenuScene(Scene):
    """a small vertical menu used by the multiplayer flow"""
    def __init__(self, game, title, options, on_back, bg="menu_play.png", sub=""):
        super().__init__(game); self.title = title; self.options = options; self.on_back = on_back; self.sub = sub
        self.bg = bg_cover(bg) if isinstance(bg, str) else bg; self.sel = 0; self.t = 0; audio.music("csm.mp3")

    def rect(self, i): return pygame.Rect(W // 2 - 620, 380 + i * 190, 1240, 160)

    def pick(self, i): audio.play("confirm"); self.options[i][2]()

    def event(self, e):
        n = len(self.options)
        if e.type == pygame.KEYDOWN:
            if e.key in (pygame.K_UP, pygame.K_w): self.sel = (self.sel - 1) % n; audio.play("hover", .5)
            elif e.key in (pygame.K_DOWN, pygame.K_s): self.sel = (self.sel + 1) % n; audio.play("hover", .5)
            elif e.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_z, pygame.K_COMMA): self.pick(self.sel)
            elif e.key == pygame.K_ESCAPE: self.on_back()
        elif e.type == pygame.MOUSEMOTION:
            for i in range(n):
                if self.rect(i).collidepoint(e.pos) and self.sel != i: self.sel = i; audio.play("hover", .5)
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            for i in range(n):
                if self.rect(i).collidepoint(e.pos): self.sel = i; self.pick(i)

    def update(self): self.t += 1

    def draw(self, surf):
        surf.blit(pygame.transform.smoothscale(self.bg, (W, H)) if self.bg.get_size() != (W, H) else self.bg, (0, 0))
        d = pygame.Surface((W, H), pygame.SRCALPHA); d.fill((0, 0, 0, 165)); surf.blit(d, (0, 0))
        text(surf, self.title, font(96 if len(self.title) < 22 else 70), GOLD, (W // 2, 120), "center", outline=6)
        if self.sub: text(surf, self.sub, font(46), WHITE, (W // 2, 230), "center", outline=4)
        for i, (lab, desc, _) in enumerate(self.options):
            r = self.rect(i); sel = i == self.sel
            if sel: r = r.inflate(30, 16)
            panel(surf, r, 240 if sel else 170, GOLD if sel else (110, 100, 140))
            text(surf, lab, font(64), GOLD if sel else WHITE, (r.centerx, r.y + 22), "midtop", outline=4)
            text(surf, desc, nfont(30, True), (235, 225, 205), (r.centerx, r.y + 104), "midtop", 2)
        text(surf, "UP / DOWN  -  ENTER confirm  -  ESC back", nfont(28, True), WHITE, (W // 2, H - 50), "center", 3)


class MPChapterScene(ChapterSelectScene):
    """chapter picker for two players - every chapter is open"""
    def __init__(self, game):
        super().__init__(game); self.unlocked = len(CHAPTERS); self.sel = 0

    def pick(self, i): audio.play("confirm"); self.game.mp_chapter_chosen(i)

    def event(self, e):
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE: self.game.mp_mode_menu(); return
        super().event(e)


class VSResultScene(EndScene):
    def __init__(self, game, w, ref):
        super().__init__(game); self.w = w; self.ref = ref; self.bg = ch_cover(ref.ch); self.t = 0
        self.make_buttons(["REMATCH", "MAIN MENU"]); audio.music("victory.mp3", loop=False)

    def pick(self, i):
        audio.play("confirm")
        if i == 1: self.game.go(MenuScene(self.game))
        else: self.game.go(FightScene(self.game, self.ref.ci, vs=True), (255, 255, 255))

    def update(self): self.t += 1

    def draw(self, surf):
        surf.blit(self.bg, (0, 0)); d = pygame.Surface((W, H), pygame.SRCALPHA); d.fill((0, 0, 0, 150)); surf.blit(d, (0, 0))
        k = clamp(self.t / 25, 0, 1); r = self.ref; p = r.players[self.w]; col = P_COL[self.w + 1]
        text(surf, "PLAYER %d WINS!" % (self.w + 1), font(int(170 * (.7 + .3 * k))), col, (W // 2, 230), "center", alpha=int(255 * k), outline=8)
        text(surf, p.name, font(80), WHITE, (W // 2, 380), "center", outline=5)
        text(surf, "Rounds   %d  -  %d" % tuple(r.vs_wins), font(60), GOLD, (W // 2, 520), "center", outline=4)
        an = hero_anim(p.char, 6.0); an.draw(surf, int(self.t * 10 / FPS) % an.n, W // 2, 860, 0, False)
        self.draw_buttons(surf)


class PrizeScene(EndScene):
    """the winner of the chapter-6 duel takes the LEGENDARY HARISSA"""
    def __init__(self, game, w, ref):
        super().__init__(game); self.w = w; self.ref = ref; self.bg = bg_cover("carthage_bg.png"); self.t = 0
        self.make_buttons(["PLAY AGAIN", "MAIN MENU"]); audio.music("victory.mp3", loop=False)
        self.hero_img = img("legend_hero.png")
        self.conf = [[random.uniform(0, W), random.uniform(-H, 0), random.uniform(3, 8), random.choice([(255, 200, 60), (255, 120, 40), (255, 240, 170), (255, 255, 255)])] for _ in range(130)]

    def pick(self, i):
        audio.play("confirm")
        if i == 1: self.game.go(MenuScene(self.game))
        else: self.game.go(MPCharScene(self.game))

    def update(self):
        self.t += 1
        for c in self.conf:
            c[1] += c[2]; c[0] += math.sin(c[1] * .02) * 2
            if c[1] > H: c[1] = -10; c[0] = random.uniform(0, W)

    def draw(self, surf):
        t = self.t; r = self.ref; win = r.players[self.w]; lose = r.players[1 - self.w]; col = P_COL[self.w + 1]
        surf.blit(self.bg, (0, 0)); d = pygame.Surface((W, H), pygame.SRCALPHA); d.fill((0, 0, 0, 170)); surf.blit(d, (0, 0))
        cx, cy = W // 2, 470
        rays = pygame.Surface((W, H), pygame.SRCALPHA)                  # rotating light beams
        for i in range(12):
            a = t * .008 + i * math.tau / 12
            pygame.draw.polygon(rays, (255, 190, 70, 34), [(cx, cy), (cx + math.cos(a - .06) * 1700, cy + math.sin(a - .06) * 1700), (cx + math.cos(a + .06) * 1700, cy + math.sin(a + .06) * 1700)])
        surf.blit(rays, (0, 0))
        g = glow_disc(430 + 30 * math.sin(t * .08), (255, 110, 20), 1.6)
        surf.blit(g, (cx - g.get_width() // 2, cy - g.get_height() // 2), special_flags=pygame.BLEND_RGB_ADD)
        for c in self.conf: pygame.draw.rect(surf, c[3], (int(c[0]), int(c[1]), 10, 16))
        can = pygame.transform.rotozoom(self.hero_img, math.sin(t * .04) * 5, .95 + .04 * math.sin(t * .07))
        surf.blit(can, can.get_rect(center=(cx, int(cy + math.sin(t * .05) * 12))))
        if t < 48:                                                      # pickup explosion from the power-up sheet
            bf = legend_frames("legend_boom.png", 6, 204, 164, 4.0)
            f = bf[min(len(bf) - 1, t // 8)]; surf.blit(f, f.get_rect(center=(cx, cy)))
        an = hero_anim(win.char, 7.0); an.draw(surf, int(t * 10 / FPS) % an.n, 330, 960 - abs(math.sin(t * .1)) * 18, 0, False)
        al = hero_anim(lose.char, 5.0); al.draw(surf, int(t * 6 / FPS) % al.n, W - 330, 960, 0, True, alpha=120)
        k = clamp(t / 25, 0, 1)
        text(surf, "PLAYER %d WINS!" % (self.w + 1), font(int(150 * (.7 + .3 * k))), col, (W // 2, 120), "center", alpha=int(255 * k), outline=8)
        text(surf, "%s claims the LEGENDARY HARISSA" % win.name, font(56), WHITE, (W // 2, 740), "center", outline=4)
        text(surf, "JOUDA  -  HARISSA DU CAP BON", font(44), GOLD, (W // 2, 805), "center", outline=4)
        self.draw_buttons(surf)


# ==============================================================================================
#  GAME  (story flow + main loop)
# ==============================================================================================
class Game:
    def __init__(self):
        self.mp = None; self.online = None
        self.char = "john"; self.blessing = 1.0; self.start_energy = 0; self.total_score = 0; self.cur_ch = 0
        self.scene = None; self.next = None; self.fade = 0.0; self.fdir = 0; self.fcolor = BLACK
        self.ov = pygame.Surface((W, H))
        self.go(MenuScene(self), speed=1000)

    @property
    def hero(self):
        if self.mp: return " & ".join(STATS[c]["name"].title() for c in self.mp["chars"])
        return STATS[self.char]["name"].title()

    def heroes(self, x=420, feet=900, scale=5.0):
        a = [Actor("hero", x, feet, anim=hero_anim(self.char, scale))]
        if self.mp: a.append(Actor("hero", x + 190, feet + 6, anim=hero_anim(self.mp["chars"][1], scale)))
        return a

    def go(self, scene, color=BLACK, speed=18):
        if self.next is not None and self.scene is not None: return
        if self.scene is None:
            self.scene = scene; return
        self.next = scene; self.fdir = 1; self.fcolor = color; self.fspeed = speed

    def toggle_fullscreen(self):
        if IS_ANDROID: return
        settings["fullscreen"] = not settings["fullscreen"]
        try: pygame.display.toggle_fullscreen()
        except Exception: pass
        save_settings()

    # -- story ------------------------------------------------------------------------------
    def hero_actor(self, x=420, feet=900, scale=5.0): return Actor("hero", x, feet, anim=hero_anim(self.char, scale))

    def after_avatar(self):
        if settings.get("unlocked", 1) > 1: self.go(ChapterSelectScene(self))
        else: self.story_airport()

    def story_airport(self):
        h = self.hero; self.blessing = 1.0; self.start_energy = 0; self.total_score = 0
        lines = [("hero", h, "Where is this guide? I hope I didn't get scammed..."),
                 ("hajj", "El Hajj", "Ah, my friend! You must be %s! Welcome to Tunisia!" % h),
                 ("hero", h, "Oh! Are you my guide? I was expecting someone... different."),
                 ("hajj", "El Hajj", "No, no. Your guide could not come. But I will take you on an adventure like no other! First, you must taste this."),
                 (None, "", "(He hands %s a spoonful of Harissa. %s hesitates, then eats it. Colors swirl, the world bends... and suddenly - %s is gone!)" % (h, h, h))]
        self.go(DialogueScene(self, "airport_bg.png", [*self.heroes(430, 905), Actor("hajj", 1250, 925, surf=nimg("el_hajj.png", 3.2))],
                              lines, lambda: self.story_chapter(0), music="elhajj.mp3"))

    def story_chapter(self, i):
        """short story scene, then the fight of chapter i"""
        h = self.hero; self.cur_ch = i
        fight = lambda: self.start_fight(i)
        if i == 0:
            lines = [("hero", h, "Finally, some fresh air... and so much sand."),
                     ("ana", "Anakin", "Sand, harissa, ruins... this planet is a mess. And you are the one who has been stirring it up."),
                     ("hero", h, "I just wanted a quiet trip. Who are you?"),
                     ("ana", "Anakin", "Call me Anakin. And I'm taking that harissa. Every last can. Come, show me what you've got!"),
                     (None, "", "(CHAPTER 1: Survive 4 waves, then face Anakin!  Press ESC in the fight to see the move list.)")]
            self.go(DialogueScene(self, "tataouine_bg.png", [*self.heroes(420, 940), Actor("ana", 1500, 940, anim=enemy_anim_idle(), flip=True)],
                                  lines, fight, music="boss.mp3", overlay=30), color=(255, 140, 30))
        elif i == 1:
            lines = [("dame", "La Dame de Carthage", "Well done, traveler. But the harissa trail leads into the old medina... and it is not empty."),
                     ("hero", h, "Why does it smell like... that?"),
                     ("dame", "La Dame de Carthage", "A strange sickness woke the dead. Their leader, Patient Zero, guards the next jar."),
                     ("hero", h, "Zombies. Of course. Why not."),
                     (None, "", "(CHAPTER 2: THE HAUNTED MEDINA - Keep moving, watch the spitters and the toxic eruptions!)")]
            self.go(DialogueScene(self, "carthage_bg.png", [*self.heroes(430, 905), Actor("dame", 1330, 760, surf=nimg("la_dame.png", 2.0), floaty=True)],
                                  lines, fight, music="elhajj.mp3", overlay=40), color=(120, 40, 200))
        elif i == 2:
            lines = [("han", "Hannibal", "You live! Few survive the medina. I crossed the Alps with elephants, you know."),
                     ("hero", h, "Yes. You mention it a lot."),
                     ("han", "Hannibal", "Raiders hold Jebel Chambi, our highest peak. Their Warlord took a jar of harissa."),
                     ("han", "Hannibal", "Take my blessing, foreigner. Do not make my elephants ashamed!"),
                     (None, "", "(CHAPTER 3: JEBEL CHAMBI - Bullets fly here. Dash through them for a PERFECT DODGE!)")]
            self.go(DialogueScene(self, "el_jem_bg.png", [*self.heroes(330, 960), Actor("han", 1560, 990, surf=nimg("hanabale.png", 3.6))],
                                  lines, fight, music="quizz.mp3"), color=(255, 90, 60))
        elif i == 3:
            lines = [("hajj", "El Hajj", "My friend! You are still alive! I am so proud. And a little surprised."),
                     ("hero", h, "El Hajj?! You did this to me!"),
                     ("hajj", "El Hajj", "The next jar is in the scrapyard. The machines there guard it. They have no taste, only lasers."),
                     ("hero", h, "I really should have read the tour agreement."),
                     (None, "", "(CHAPTER 4: THE SCRAPYARD - Robots explode when they die. Don't stand too close to the Mega Destroyer's meteors!)")]
            self.go(DialogueScene(self, "airport_bg.png", [*self.heroes(430, 905), Actor("hajj", 1250, 925, surf=nimg("el_hajj.png", 3.2))],
                                  lines, fight, music="elhajj.mp3"), color=(60, 140, 255))
        else:
            lines = [("ana", "Dark Anakin", "You beat my sand, my zombies, my raiders, my machines. Impressive. Annoying, but impressive."),
                     ("hero", h, "Give back the harissa. All of it."),
                     ("ana", "Dark Anakin", "The last jar sits on my summit, and I have gathered everyone you defeated. Come and take it!"),
                     ("hero", h, "Fine. Let's finish this. Ultimate ready!"),
                     (None, "", "(CHAPTER 5: THE SUMMIT - Everyone is back. Save your ULTIMATE for Dark Anakin!)")]
            self.go(DialogueScene(self, "tataouine_bg.png", [*self.heroes(420, 940), Actor("ana", 1500, 940, anim=family_or_dark(), flip=True)],
                                  lines, fight, music="boss.mp3", overlay=70), color=(150, 80, 255))

    def start_fight(self, i):
        self.cur_ch = i; self.go(FightScene(self, i), (255, 255, 255))

    # -- online play hooks (see online_scenes.py) ---------------------------------------------
    def net_result(self, fight, kind):
        from online_scenes import NetResultScene
        self.go(NetResultScene(self, fight, kind), (255, 255, 255))

    def net_lost(self, msg):
        from online_scenes import NetMessageScene
        self.drop_online(); self.go(NetMessageScene(self, msg))

    def net_leave(self):
        self.drop_online(); self.go(MenuScene(self))

    def drop_online(self):
        if self.online:
            try: self.online.close()
            except Exception: pass
        self.online = None

    def fight_over(self, fight):
        if getattr(fight, "net", None): self.net_result(fight, "lose")
        else: self.go(GameOverScene(self, "fight", fight))

    def chapter_done(self, fight):
        if getattr(fight, "net", None): self.net_result(fight, "win"); return
        i = fight.ci; self.total_score += fight.score
        settings["unlocked"] = max(settings.get("unlocked", 1), min(len(CHAPTERS), i + 2)); save_settings()
        self.blessing = 1 + 0.05 * (i + 1); self.start_energy = 10 * (i + 1)
        if i + 1 < len(CHAPTERS): self.go(ChapterClearScene(self, fight), (255, 255, 255))
        elif self.mp and self.mp.get("story"): self.mp_chapter6()
        else: self.go(VictoryScene(self, fight), (255, 255, 255))

    # -- multiplayer flow -------------------------------------------------------------------
    def mp_mode_menu(self):
        c = self.mp["chars"]; sub = "P1: %s        P2: %s" % (STATS[c[0]]["name"], STATS[c[1]]["name"])
        self.go(MPMenuScene(self, "CHOOSE MODE", [
            ("STORY  (TEAM)", "Chapters 1-5 together... then CHAPTER 6: a duel for the LEGENDARY HARISSA!", self.mp_story),
            ("CHOOSE A CHAPTER", "Pick any chapter, then play it as a TEAM or fight each other (VERSUS).",
             lambda: self.go(MPChapterScene(self)))], on_back=lambda: self.go(MPCharScene(self)), sub=sub))

    def mp_story(self):
        self.mp.update(story=True, vs=False, final=False); self.blessing = 1.0; self.start_energy = 0; self.total_score = 0
        self.story_airport()

    def mp_chapter_chosen(self, i):
        self.mp.update(story=False, vs=False, final=False, ci=i); ch = CHAPTERS[i]
        self.go(MPMenuScene(self, "CHAPTER %d:  %s" % (ch["num"], ch["name"].upper()), [
            ("TEAM  (CO-OP)", "Fight the chapter together - two heroes, one goal.", lambda: self.mp_play_coop(i)),
            ("VERSUS", "No waves - fight each other in this arena. Best of 3 rounds.", lambda: self.mp_play_vs(i))],
            on_back=lambda: self.go(MPChapterScene(self)), bg=ch_cover(ch)))

    def mp_play_coop(self, i):
        self.mp.update(vs=False, story=False); self.blessing = 1 + 0.05 * i; self.start_energy = 10 * i; self.total_score = 0
        if i == 0: self.story_airport()
        else: self.story_chapter(i)

    def mp_play_vs(self, i):
        self.mp.update(vs=True, final=False); self.blessing = 1.0; self.start_energy = 0
        self.go(FightScene(self, i, vs=True), (255, 255, 255))

    def mp_chapter6(self):
        self.mp.update(final=True, vs=True)
        c1, c2 = self.mp["chars"]; n1, n2 = STATS[c1]["name"].title(), STATS[c2]["name"].title()
        lines = [(None, "", "(The summit trembles... the last jar cracks open, and a golden light fills the sky.)"),
                 ("hajj", "El Hajj", "Behold! The LEGENDARY HARISSA of Cap Bon! One can. One legend. And only ONE of you may take it."),
                 ("hero", n1, "I did most of the work out there. It's mine."),
                 ("hero2", n2, "Dream on! Who saved your back in every single chapter? I'm taking it!"),
                 ("hajj", "El Hajj", "Then settle it the Tunisian way. Fight! The winner takes the Legendary Harissa."),
                 (None, "", "(CHAPTER 6: THE LEGENDARY DUEL - Best of 3 rounds.  P1 and P2: fight!)")]
        actors = [Actor("hero", 380, 960, anim=hero_anim(c1, 5.0)), Actor("hero2", 1540, 960, anim=hero_anim(c2, 5.0), flip=True),
                  Actor("can", W // 2, 760, surf=nimg("legend_hero.png", .85), floaty=True)]
        self.go(DialogueScene(self, "tataouine_bg.png", actors, lines,
                              lambda: self.go(FightScene(self, 4, vs=True, final=True), (255, 150, 40)), music="boss.mp3", overlay=60), color=(255, 190, 80))

    def vs_done(self, fight):
        if getattr(fight, "net", None): self.net_result(fight, "vs"); return
        w = fight.vs_winner
        if self.mp.get("final"): self.go(PrizeScene(self, w, fight), (255, 220, 120))
        else: self.go(VSResultScene(self, w, fight), (255, 255, 255))

    # -- loop -------------------------------------------------------------------------------
    def run(self):
        while True:
            for e in pygame.event.get():
                if e.type == pygame.QUIT: save_settings(); pygame.quit(); sys.exit()
                if e.type == pygame.KEYDOWN and e.key == pygame.K_F11: self.toggle_fullscreen(); continue
                if IS_ANDROID:
                    e = self.android_event(e)
                    if e is None: continue
                if self.fdir == 0: self.scene.event(e)
            self.step(screen)
            present(screen); clock.tick(FPS)

    def android_event(self, e):
        """Touch -> game coordinates, plus mouse emulation so every menu works with a finger.
        Returns the event to deliver (or None when it was fully handled here)."""
        t = e.type
        if t in (pygame.FINGERDOWN, pygame.FINGERUP, pygame.FINGERMOTION):
            gx, gy = to_game_xy(e.x, e.y)
            fe = pygame.event.Event(t, x=gx / W, y=gy / H, finger_id=e.finger_id, dx=0.0, dy=0.0, pressure=1.0)
            if self.fdir == 0:
                pos = (int(gx), int(gy))
                self.scene.event(fe)                                           # joystick / buttons in the fight scene
                if t == pygame.FINGERDOWN:
                    self.scene.event(pygame.event.Event(pygame.MOUSEMOTION, pos=pos, rel=(0, 0), buttons=(1, 0, 0), touch=True))
                    self.scene.event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1, touch=True))
                elif t == pygame.FINGERMOTION:
                    self.scene.event(pygame.event.Event(pygame.MOUSEMOTION, pos=pos, rel=(0, 0), buttons=(1, 0, 0), touch=True))
                else:
                    self.scene.event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=1, touch=True))
            return None
        if t in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION):
            return None                                                        # SDL's own touch->mouse copy (wrong scale): ignore
        if t == pygame.KEYDOWN and getattr(e, "key", None) == getattr(pygame, "K_AC_BACK", -1):
            return pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode="", scancode=0)   # phone's Back button
        return e

    def step(self, surf):
        # fade handling
        if self.fdir == 1:
            self.fade += self.fspeed
            if self.fade >= 255:
                self.fade = 255; self.scene = self.next; self.next = None; self.fdir = -1; self.scene.enter()
        elif self.fdir == -1:
            self.fade -= self.fspeed
            if self.fade <= 0: self.fade = 0; self.fdir = 0
        self.scene.update()
        self.scene.draw(surf)
        if self.fade > 0:
            self.ov.fill(self.fcolor); self.ov.set_alpha(int(self.fade)); surf.blit(self.ov, (0, 0))


def enemy_anim_idle():
    return sith_art(None, 5.0)["idle"]


def family_or_dark():
    return sith_art((70, 0, 120), 5.4)["idle"]


def main():
    g = Game(); args = sys.argv[1:]
    for a in args:
        if a.startswith("--char="): g.char = a.split("=")[1]
    if "--fight" in args:
        ci = 0
        for a in args:
            if a.startswith("--chapter="): ci = clamp(int(a.split("=")[1]) - 1, 0, len(CHAPTERS) - 1)
        g.scene = FightScene(g, ci)
    elif "--select" in args: settings["unlocked"] = 5; g.scene = ChapterSelectScene(g)
    elif "--avatar" in args: g.scene = AvatarScene(g)
    g.run()


if __name__ == "__main__":
    main()
