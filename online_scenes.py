"""
online_scenes.py  --  menus for online play (host / join / lobby / result).
Imported lazily by full_game.py, after full_game's own classes exist.
"""
import math, random, time, threading
import pygame
import full_game as G
from full_game import (Scene, EndScene, W, H, FPS, text, font, nfont, panel, rrect, bg_cover, ch_cover, audio, clamp,
                       GOLD, WHITE, BLACK, P_COL, CHAPTERS, STATS, hero_anim, FightScene, MenuScene, settings, save_settings)
import netplay

CHARS = ["john", "jane"]


def my_name():
    return str(settings.get("player_name") or "Player")[:16]


class Session:
    """the live connection + lobby choices; lives in game.online"""
    def __init__(self, link, is_host, peer_name, host_obj=None):
        self.link = link; self.is_host = is_host; self.peer_name = peer_name; self.name = my_name(); self.host_obj = host_obj
        self.my_char = "john"; self.peer_char = "jane"; self.mode = "coop"; self.ch = 0
        self.peer_ready = False; self.my_ready = False; self.rtt = 0.05

    def close(self):
        try: self.link.close()
        except Exception: pass
        if self.host_obj: self.host_obj.close()


# ------------------------------------------------------------------------------------------------
#  tiny button toolkit (mouse / finger / keyboard)
# ------------------------------------------------------------------------------------------------
class Btn:
    def __init__(self, rect, label, fn, size=44, enabled=True, color=None):
        self.rect = pygame.Rect(rect); self.label = label; self.fn = fn; self.size = size; self.enabled = enabled; self.color = color


class OnlineScene(Scene):
    bgname = "menu_play.png"

    def __init__(self, game):
        super().__init__(game)
        self.bg = bg_cover(self.bgname); self.t = 0; self.btns = []; self.sel = 0; self.toast = ""; self.toast_t = 0
        audio.music("csm.mp3")

    def say(self, msg): self.toast = msg; self.toast_t = 240

    def live(self): return [b for b in self.btns if b.enabled]

    def click(self, b):
        if not b.enabled: audio.play("false", .5); return
        audio.play("confirm"); b.fn()

    def event(self, e):
        if e.type == pygame.MOUSEMOTION:
            for i, b in enumerate(self.btns):
                if b.enabled and b.rect.collidepoint(e.pos) and self.sel != i: self.sel = i; audio.play("hover", .4)
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            for i, b in enumerate(self.btns):
                if b.rect.collidepoint(e.pos): self.sel = i; self.click(b); return
        elif e.type == pygame.KEYDOWN:
            if self.key(e): return
            n = len(self.btns)
            if not n: return
            if e.key in (pygame.K_DOWN, pygame.K_RIGHT, pygame.K_TAB):
                self.sel = (self.sel + 1) % n; audio.play("hover", .4)
            elif e.key in (pygame.K_UP, pygame.K_LEFT):
                self.sel = (self.sel - 1) % n; audio.play("hover", .4)
            elif e.key in (pygame.K_RETURN, pygame.K_SPACE): self.click(self.btns[self.sel])
            elif e.key == pygame.K_ESCAPE: self.back()

    def key(self, e): return False
    def back(self): pass

    def draw_bg(self, surf, dim=165):
        surf.blit(self.bg, (0, 0))
        d = pygame.Surface((W, H), pygame.SRCALPHA); d.fill((0, 0, 0, dim)); surf.blit(d, (0, 0))

    def draw_btns(self, surf):
        for i, b in enumerate(self.btns):
            sel = i == self.sel and b.enabled
            r = b.rect.inflate(14, 8) if sel else b.rect
            if not b.enabled:
                rrect(surf, (45, 40, 55), r, 18); rrect(surf, (90, 85, 100), r, 18, 2)
                text(surf, b.label, font(b.size), (120, 115, 130), r.center, "center", shadow=0)
            else:
                col = b.color or ((255, 190, 60) if sel else (55, 45, 75))
                rrect(surf, col if (sel or b.color) else (55, 45, 75), r, 18)
                rrect(surf, WHITE if sel else (150, 130, 190), r, 18, 3 if sel else 2)
                text(surf, b.label, font(b.size), BLACK if (sel or b.color) else WHITE, r.center, "center", shadow=0)

    def draw_toast(self, surf):
        if self.toast_t:
            self.toast_t -= 1
            text(surf, self.toast, font(40), (255, 120, 100), (W // 2, H - 60), "center", alpha=min(255, self.toast_t * 6), outline=4)

    def update(self): self.t += 1


# ------------------------------------------------------------------------------------------------
#  entry: LOCAL or ONLINE
# ------------------------------------------------------------------------------------------------
class PlayModeScene(OnlineScene):
    def __init__(self, game):
        super().__init__(game)
        self.btns = [Btn((W // 2 - 600, 340, 1200, 170), "ONLINE  -  WiFi / Hotspot", self.online, 64),
                     Btn((W // 2 - 600, 560, 1200, 170), "LOCAL  -  same device / keyboard", self.local, 64),
                     Btn((W // 2 - 200, 820, 400, 100), "BACK", self.back, 48)]

    def online(self): self.game.go(OnlineMenuScene(self.game))
    def local(self): self.game.go(G.MPCharScene(self.game))
    def back(self): self.game.go(MenuScene(self.game))

    def draw(self, surf):
        self.draw_bg(surf)
        text(surf, "MULTIPLAYER", font(110), GOLD, (W // 2, 120), "center", outline=6)
        text(surf, "Play with a friend", font(46), WHITE, (W // 2, 230), "center", outline=4)
        self.draw_btns(surf)
        text(surf, "ONLINE: two phones / PCs on the same WiFi, or one phone's hotspot (no internet needed)",
             nfont(30, True), (235, 225, 205), (W // 2, 770), "center", 3)


class OnlineMenuScene(OnlineScene):
    def __init__(self, game):
        super().__init__(game)
        self.btns = [Btn((W // 2 - 600, 340, 1200, 170), "HOST A GAME", self.host, 70),
                     Btn((W // 2 - 600, 560, 1200, 170), "JOIN A GAME", self.join, 70),
                     Btn((W // 2 - 200, 820, 400, 100), "BACK", self.back, 48)]

    def host(self): self.game.go(HostScene(self.game))
    def join(self): self.game.go(JoinScene(self.game))
    def back(self): self.game.go(PlayModeScene(self.game))

    def draw(self, surf):
        self.draw_bg(surf)
        text(surf, "PLAY ONLINE", font(110), GOLD, (W // 2, 120), "center", outline=6)
        text(surf, "Same WiFi  -  Router / LAN  -  Phone hotspot", font(46), WHITE, (W // 2, 230), "center", outline=4)
        self.draw_btns(surf)
        text(surf, "One player HOSTS, the other JOINS.  Both phones must be on the same network.", nfont(30, True),
             (235, 225, 205), (W // 2, 770), "center", 3)


# ------------------------------------------------------------------------------------------------
#  HOST
# ------------------------------------------------------------------------------------------------
class HostScene(OnlineScene):
    def __init__(self, game):
        super().__init__(game)
        self.host = None; self.err = ""
        try: self.host = netplay.Host(my_name())
        except Exception as ex: self.err = "Can't open the room: %s" % ex
        self.btns = [Btn((W // 2 - 200, 880, 400, 100), "CANCEL", self.back, 48)]

    def back(self):
        if self.host: self.host.close()
        self.game.go(OnlineMenuScene(self.game))

    def update(self):
        self.t += 1
        h = self.host
        if h and h.link is not None:
            sess = Session(h.link, True, h.peer_name, host_obj=h); self.game.online = sess
            self.host = None; self.game.go(LobbyScene(self.game, sess), (255, 255, 255))

    def draw(self, surf):
        self.draw_bg(surf)
        text(surf, "YOUR ROOM IS OPEN", font(100), GOLD, (W // 2, 110), "center", outline=6)
        dots = "." * (1 + (self.t // 25) % 3)
        text(surf, "Waiting for a friend" + dots, font(60), WHITE, (W // 2, 250), "center", outline=4)
        panel(surf, pygame.Rect(W // 2 - 760, 340, 1520, 440))
        if self.err:
            text(surf, self.err, font(46), (255, 120, 100), (W // 2, 560), "center", outline=4)
        else:
            ips = self.host.ips if self.host else []
            text(surf, "Your friend:  PLAY  >  MULTIPLAYER  >  ONLINE  >  JOIN A GAME", nfont(38, True), WHITE, (W // 2, 380), "center", 3)
            text(surf, "(your room appears by itself)", nfont(30, True), (200, 195, 215), (W // 2, 430), "center", 3)
            text(surf, "If it doesn't, they can choose  TYPE IP  and enter:", nfont(32, True), (235, 225, 205), (W // 2, 520), "center", 3)
            ip = ips[0] if ips else "turn on WiFi / hotspot"
            text(surf, ip, font(96), GOLD, (W // 2, 620), "center", outline=5)
            if len(ips) > 1: text(surf, "also:  " + "   ".join(ips[1:3]), nfont(30, True), (200, 195, 215), (W // 2, 720), "center", 3)
        a = self.t * 0.08
        for i in range(8):
            r = 10 + 6 * math.sin(a + i)
            pygame.draw.circle(surf, GOLD, (int(W // 2 + math.cos(a * .5 + i * .785) * 90), int(850 + math.sin(a * .5 + i * .785) * 0)), int(r))
        self.draw_btns(surf)


# ------------------------------------------------------------------------------------------------
#  JOIN
# ------------------------------------------------------------------------------------------------
class JoinScene(OnlineScene):
    def __init__(self, game):
        super().__init__(game)
        self.scan = None
        try: self.scan = netplay.Scanner()
        except Exception: pass
        self.keypad = False; self.ip = settings.get("last_ip", ""); self.busy = False; self.result = None
        self.rows = []; self.build()

    def stop(self):
        if self.scan: self.scan.close()

    def build(self):
        hosts = self.scan.hosts() if self.scan else []
        self.rows = hosts[:4]
        old = self.btns[self.sel].label if self.btns and self.sel < len(self.btns) else None
        self.btns = []
        if self.keypad:
            kx, ky, s = W // 2 - 330, 360, 150
            keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", ".", "0", "<"]
            for i, k in enumerate(keys):
                self.btns.append(Btn((kx + (i % 3) * (s + 20), ky + (i // 3) * (s - 20), s, s - 30), k, (lambda k=k: self.press(k)), 64))
            self.btns.append(Btn((W // 2 + 200, 360, 360, 200), "CONNECT", self.connect_ip, 54, enabled=bool(self.ip) and not self.busy, color=(90, 200, 110)))
            self.btns.append(Btn((W // 2 + 200, 590, 360, 200), "CANCEL", self.close_keypad, 50))
        else:
            for i, (ip, name, port) in enumerate(self.rows):
                self.btns.append(Btn((W // 2 - 600, 330 + i * 125, 1200, 105), "%s    %s" % (name, ip), (lambda ip=ip, port=port: self.connect(ip, port)), 54, enabled=not self.busy))
            self.btns.append(Btn((W // 2 - 600, 850, 580, 100), "TYPE IP", self.open_keypad, 48))
            self.btns.append(Btn((W // 2 + 20, 850, 580, 100), "BACK", self.back, 48))
        self.sel = min(self.sel, max(0, len(self.btns) - 1))

    def back(self):
        self.stop(); self.game.go(OnlineMenuScene(self.game))

    def open_keypad(self): self.keypad = True; self.sel = 0; self.build()
    def close_keypad(self): self.keypad = False; self.sel = 0; self.build()

    def press(self, k):
        if k == "<": self.ip = self.ip[:-1]
        elif len(self.ip) < 15: self.ip += k
        self.build()

    def key(self, e):
        if not self.keypad: return False
        if e.key == pygame.K_BACKSPACE: self.press("<"); return True
        if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and self.ip: self.connect_ip(); return True
        if e.key == pygame.K_ESCAPE: self.close_keypad(); return True
        ch = e.unicode
        if ch and ch in "0123456789.": self.press(ch); return True
        return False

    def connect_ip(self):
        ip = self.ip.strip()
        if ip.count(".") != 3 or not all(p.isdigit() and 0 <= int(p) < 256 for p in ip.split(".")):
            self.say("That doesn't look like an IP address"); return
        settings["last_ip"] = ip; save_settings()
        self.connect(ip, netplay.PORT_TCP)

    def connect(self, ip, port):
        if self.busy: return
        self.busy = True; self.result = None; self.build()

        def work():
            try: self.result = ("ok",) + netplay.connect(ip, port, my_name())
            except IOError as ex: self.result = ("err", str(ex))
        threading.Thread(target=work, daemon=True).start()

    def update(self):
        self.t += 1
        if self.t % 20 == 0 and not self.busy and not self.keypad:
            if [r[0] for r in self.rows] != [h[0] for h in (self.scan.hosts() if self.scan else [])][:4]: self.build()
        r = self.result
        if r:
            self.result = None; self.busy = False
            if r[0] == "ok":
                self.stop(); sess = Session(r[1], False, r[2]); self.game.online = sess
                self.game.go(LobbyScene(self.game, sess), (255, 255, 255))
            else:
                self.say(r[1]); self.build()

    def draw(self, surf):
        self.draw_bg(surf)
        text(surf, "JOIN A GAME", font(100), GOLD, (W // 2, 100), "center", outline=6)
        if self.keypad:
            text(surf, "Enter the host's IP address", font(46), WHITE, (W // 2, 215), "center", outline=4)
            r = pygame.Rect(W // 2 - 330, 270, 1090, 80); panel(surf, r)
            text(surf, (self.ip or "") + ("_" if (self.t // 20) % 2 else ""), font(66), GOLD, (r.x + 30, r.centery), "midleft", outline=4)
        else:
            dots = "." * (1 + (self.t // 25) % 3)
            if self.rows: text(surf, "Rooms found - tap one", font(46), WHITE, (W // 2, 215), "center", outline=4)
            else:
                text(surf, "Searching for rooms on this network" + dots, font(46), WHITE, (W // 2, 215), "center", outline=4)
                text(surf, "Ask your friend to press  HOST A GAME", nfont(34, True), (235, 225, 205), (W // 2, 420), "center", 3)
                text(surf, "Same WiFi - or connect to your friend's hotspot first", nfont(30, True), (200, 195, 215), (W // 2, 480), "center", 3)
        if self.busy: text(surf, "Connecting...", font(56), GOLD, (W // 2, 800), "center", outline=4)
        self.draw_btns(surf); self.draw_toast(surf)


# ------------------------------------------------------------------------------------------------
#  LOBBY
# ------------------------------------------------------------------------------------------------
class LobbyScene(OnlineScene):
    bgname = "bgcsp.png"

    def __init__(self, game, sess):
        super().__init__(game); self.s = sess; self.ping_t = 0; self.pending = None
        sess.my_ready = False; sess.peer_ready = False
        self.build()
        self.sync_all()

    # -- layout ---------------------------------------------------------------------------------
    def build(self):
        s = self.s; self.btns = []
        self.btns.append(Btn((60, 40, 260, 80), "LEAVE", self.leave, 40))
        for i, c in enumerate(CHARS):
            self.btns.append(Btn((210 + i * 330, 640, 300, 90), STATS[c]["name"], (lambda c=c: self.pick_char(c)), 46,
                                 color=(255, 190, 60) if s.my_char == c else None))
        if s.is_host:
            self.btns.append(Btn((120, 800, 560, 100), "MODE:  " + ("CO-OP" if s.mode == "coop" else "VERSUS"), self.toggle_mode, 46))
            self.btns.append(Btn((700, 800, 110, 100), "<", (lambda: self.chap(-1)), 56))
            self.btns.append(Btn((1210, 800, 110, 100), ">", (lambda: self.chap(1)), 56))
            self.btns.append(Btn((W - 560, 800, 460, 100), "START", self.start, 60, enabled=s.peer_ready, color=(90, 200, 110) if s.peer_ready else None))
        else:
            self.btns.append(Btn((W - 760, 800, 660, 100), "READY!" if not s.my_ready else "READY  (tap to cancel)", self.toggle_ready, 52,
                                 color=(90, 200, 110) if s.my_ready else None))
        self.sel = min(self.sel, len(self.btns) - 1)

    def leave(self):
        self.s.close(); self.game.online = None; self.game.go(MenuScene(self.game))

    def back(self): self.leave()

    def pick_char(self, c):
        self.s.my_char = c; self.s.link.send({"t": "char", "c": c}); self.build()

    def toggle_mode(self):
        self.s.mode = "vs" if self.s.mode == "coop" else "coop"; self.sync_cfg(); self.build()

    def chap(self, d):
        self.s.ch = (self.s.ch + d) % len(CHAPTERS); self.sync_cfg(); self.build()

    def toggle_ready(self):
        self.s.my_ready = not self.s.my_ready; self.s.link.send({"t": "ready", "v": self.s.my_ready}); self.build()

    def sync_cfg(self): self.s.link.send({"t": "cfg", "mode": self.s.mode, "ch": self.s.ch})

    def sync_all(self):
        self.s.link.send({"t": "char", "c": self.s.my_char})
        if self.s.is_host: self.sync_cfg()
        else: self.s.link.send({"t": "ready", "v": False})

    # -- start ----------------------------------------------------------------------------------
    def start(self):
        s = self.s
        if not s.peer_ready: return
        delay = int(clamp(math.ceil(s.rtt * 1000.0 / 2 / 16.7) + 2, 3, 9))
        msg = {"t": "start", "seed": netplay.new_seed(), "mode": s.mode, "ch": s.ch, "chars": [s.my_char, s.peer_char], "delay": delay}
        s.link.send(msg); self.pending = msg

    def begin(self, m):
        g = self.game
        if g.next is not None or g.fdir != 0: self.pending = m; return
        s = self.s; vs = m["mode"] == "vs"; ch = int(m["ch"]) % len(CHAPTERS)
        g.mp = dict(chars=list(m["chars"]), story=False, vs=vs, final=False, ci=ch)
        g.blessing = 1.0; g.start_energy = 0; g.total_score = 0
        ls = netplay.Lockstep(s.link, s.is_host, int(m["seed"]), int(m.get("delay", 4)))
        self.started = True
        g.go(FightScene(g, ch, vs=vs, net=ls), (255, 255, 255))

    started = False

    # -- network pump ---------------------------------------------------------------------------
    def update(self):
        self.t += 1; s = self.s
        if self.started: return
        if self.pending:
            m, self.pending = self.pending, None; self.begin(m); return
        while True:
            m = s.link.poll()
            if m is None: break
            t = m.get("t")
            if t == "char": s.peer_char = m.get("c") if m.get("c") in CHARS else "jane"
            elif t == "cfg" and not s.is_host:
                s.mode = "vs" if m.get("mode") == "vs" else "coop"; s.ch = int(m.get("ch", 0)) % len(CHAPTERS)
            elif t == "ready" and s.is_host: s.peer_ready = bool(m.get("v")); self.build()
            elif t == "ping": s.link.send({"t": "pong", "ts": m.get("ts")})
            elif t == "pong":
                try: s.rtt = s.rtt * .7 + max(0.0, time.time() - float(m["ts"])) * .3
                except Exception: pass
            elif t == "start" and not s.is_host:
                self.begin(m); return
            elif t == "bye":
                self.game.net_lost("%s left the lobby" % s.peer_name); return
        if s.link.closed or s.link.silent_for() > 12:
            self.game.net_lost("Connection lost"); return
        if self.t % 30 == 0: s.link.send({"t": "ping", "ts": time.time()})

    # -- draw -----------------------------------------------------------------------------------
    def draw_hero(self, surf, char, cx, flip, ready_txt, tint_col):
        an = hero_anim(char, 5.0)
        an.draw(surf, int(self.t * 10 / FPS) % an.n, cx, 610, 0, flip)

    def draw(self, surf):
        s = self.s
        self.draw_bg(surf, 150)
        text(surf, "ONLINE LOBBY", font(90), GOLD, (W // 2, 70), "center", outline=6)
        text(surf, "%s   (P%d)   vs / with   %s   (P%d)" % (s.name, 1 if s.is_host else 2, s.peer_name, 2 if s.is_host else 1),
             nfont(34, True), WHITE, (W // 2, 150), "center", 3)
        mine = pygame.Rect(120, 190, 840, 560); theirs = pygame.Rect(W - 960, 190, 840, 560)
        panel(surf, mine, 190, P_COL[1 if s.is_host else 2]); panel(surf, theirs, 190, P_COL[2 if s.is_host else 1])
        text(surf, "YOU", font(54), P_COL[1 if s.is_host else 2], (mine.centerx, mine.y + 14), "midtop", outline=4)
        text(surf, s.peer_name.upper(), font(54), P_COL[2 if s.is_host else 1], (theirs.centerx, theirs.y + 14), "midtop", outline=4)
        self.draw_hero(surf, s.my_char, mine.centerx, False, "", None)
        self.draw_hero(surf, s.peer_char, theirs.centerx, True, "", None)
        text(surf, STATS[s.peer_char]["name"], font(46), WHITE, (theirs.centerx, 650), "center", outline=4)
        if s.is_host:
            st = "READY" if s.peer_ready else "choosing..."
            text(surf, st, font(46), (110, 230, 120) if s.peer_ready else (200, 195, 215), (theirs.centerx, 700), "center", outline=4)
        else:
            text(surf, "HOST", font(40), GOLD, (theirs.centerx, 700), "center", outline=4)
        # chapter / mode strip
        ch = CHAPTERS[s.ch]
        strip = pygame.Rect(830, 800, 370, 100)
        text(surf, "CH %d" % ch["num"], font(40), GOLD, (strip.centerx, strip.y + 4), "midtop", outline=3)
        text(surf, ch["name"], font(30 if len(ch["name"]) < 14 else 24), WHITE, (strip.centerx, strip.y + 56), "midtop", outline=3)
        if not s.is_host:
            text(surf, "%s  -  Chapter %d: %s" % ("CO-OP" if s.mode == "coop" else "VERSUS", ch["num"], ch["name"]), nfont(34, True), WHITE, (W // 2, 960), "center", 3)
            text(surf, "Tap READY, then wait for the host to start", nfont(30, True), (200, 195, 215), (W // 2 - 400, 840), "center", 3)
        else:
            text(surf, "VERSUS = duel, best of 3     CO-OP = beat the chapter together", nfont(28, True), (200, 195, 215), (W // 2, 960), "center", 3)
            if not s.peer_ready: text(surf, "waiting for your friend to be READY", nfont(28, True), (255, 200, 120), (W - 330, 920), "center", 3)
        text(surf, "ping %d ms" % int(s.rtt * 1000), nfont(24, True), (170, 170, 190), (W - 20, 10), "topright", 2)
        self.draw_btns(surf)


# ------------------------------------------------------------------------------------------------
#  RESULT / ERROR
# ------------------------------------------------------------------------------------------------
class NetResultScene(EndScene):
    def __init__(self, game, fight, kind):
        super().__init__(game); self.f = fight; self.kind = kind; self.t = 0; self.bg = ch_cover(fight.ch)
        self.make_buttons(["BACK TO LOBBY", "DISCONNECT"]); audio.music("victory.mp3" if kind != "lose" else "gameover.mp3", loop=False)
        s = game.online; self.me = 1 if (s and s.is_host) else 2

    def pick(self, i):
        audio.play("confirm")
        s = self.game.online
        if i == 1 or s is None or s.link.closed: self.game.net_leave(); return
        self.game.go(LobbyScene(self.game, s))

    def update(self): self.t += 1

    def draw(self, surf):
        f = self.f; k = clamp(self.t / 25, 0, 1)
        surf.blit(self.bg, (0, 0)); d = pygame.Surface((W, H), pygame.SRCALPHA); d.fill((0, 0, 0, 150)); surf.blit(d, (0, 0))
        if self.kind == "vs":
            w = f.vs_winner; col = P_COL[w + 1]
            text(surf, "PLAYER %d WINS!" % (w + 1), font(int(170 * (.7 + .3 * k))), col, (W // 2, 230), "center", alpha=int(255 * k), outline=8)
            text(surf, f.players[w].name, font(80), WHITE, (W // 2, 380), "center", outline=5)
            text(surf, "Rounds   %d  -  %d" % tuple(f.vs_wins), font(60), GOLD, (W // 2, 520), "center", outline=4)
            text(surf, "YOU WON!" if w + 1 == self.me else "You lost - rematch!", font(56), (110, 230, 120) if w + 1 == self.me else (255, 150, 120), (W // 2, 640), "center", outline=4)
        else:
            win = self.kind == "win"
            text(surf, "VICTORY!" if win else "DEFEAT", font(int(190 * (.7 + .3 * k))), GOLD if win else (230, 60, 60), (W // 2, 270), "center", alpha=int(255 * k), outline=8)
            text(surf, "Chapter %d: %s" % (f.ch["num"], f.ch["name"]), font(52), WHITE, (W // 2, 440), "center", outline=4)
            secs = f.time / 60.0
            text(surf, "Score %d      Best combo %d      Enemies beaten %d      Time %d:%02d" % (f.score, f.max_combo, f.kills, secs // 60, secs % 60),
                 nfont(38, True), GOLD, (W // 2, 560), "center", 3)
        self.draw_buttons(surf)


class NetMessageScene(EndScene):
    def __init__(self, game, msg):
        super().__init__(game); self.msg = msg; self.bg = bg_cover("menu_play.png"); self.t = 0
        self.make_buttons(["MAIN MENU"]); audio.music("csm.mp3")

    def pick(self, i): audio.play("confirm"); self.game.go(MenuScene(self.game))
    def update(self): self.t += 1

    def draw(self, surf):
        surf.blit(self.bg, (0, 0)); d = pygame.Surface((W, H), pygame.SRCALPHA); d.fill((0, 0, 0, 170)); surf.blit(d, (0, 0))
        text(surf, "DISCONNECTED", font(110), (230, 80, 70), (W // 2, 320), "center", outline=6)
        text(surf, self.msg, font(52), WHITE, (W // 2, 500), "center", outline=4)
        self.draw_buttons(surf)
