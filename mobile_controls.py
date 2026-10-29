"""
Mobile touch controls for Spicy John.
Draws a virtual joystick (left) + action buttons (right) and feeds
synthetic input into the FightScene / menus.
"""
import pygame

W, H = 1920, 1080


def rect(x, y, w, h): return pygame.Rect(int(x), int(y), int(w), int(h))


class TouchControls:
    """Persistent HUD overlay for the fight scene."""

    def __init__(self):
        self.joy_c = (235, H - 250)          # joystick centre
        self.joy_r = 150                     # joystick radius
        self.knob_r = 66
        self.press = {}                      # id -> ("joy"|"btn", name)
        self.joy_vec = (0.0, 0.0)            # -1..1
        self.held = dict(left=False, right=False, up=False, down=False)
        self.buttons = []                    # (rect, name, label, color)
        self.pause_label = "PAUSE"
        self._build_buttons()
        self.pause_btn = rect(W - 170, 96, 140, 70)
        self.active = False

    def _build_buttons(self):
        # right-hand cluster, every circle fully on screen (1920x1080 game space)
        R = 82
        spec = [("light", "ATK", (W - 210, H - 200), (255, 160, 40)),
                ("heavy", "HEAVY", (W - 392, H - 132), (230, 70, 70)),
                ("special", "SPEC", (W - 210, H - 396), (80, 170, 255)),
                ("jump", "JUMP", (W - 410, H - 322), (90, 220, 110)),
                ("dash", "DASH", (W - 600, H - 190), (200, 120, 255)),
                ("ult", "ULT", (W - 600, H - 396), (255, 215, 60))]
        self.buttons = [(rect(cx - R, cy - R, R * 2, R * 2), name, lab, col) for name, lab, (cx, cy), col in spec]

    # ---------- event handling ----------------------------------------------------------
    def handle(self, e, fight):
        """Return True if the event was consumed by the touch UI."""
        t = e.type
        if t == pygame.FINGERDOWN:
            x, y = e.x * W, e.y * H
            # pause button
            if self.pause_btn.collidepoint(x, y):
                fight.toggle_pause()
                return True
            # buttons
            for r, name, lab, col in self.buttons:
                if pygame.math.Vector2(x, y).distance_to(r.center) <= r.w * 0.58:
                    self.press[e.finger_id] = ("btn", name)
                    fight.push_press(name)
                    return True
            # joystick
            if pygame.math.Vector2(x, y).distance_to(self.joy_c) < self.joy_r * 1.6:
                self.press[e.finger_id] = ("joy", None)
                self._move_joy(x, y)
                return True
        elif t == pygame.FINGERMOTION:
            if e.finger_id in self.press and self.press[e.finger_id][0] == "joy":
                self._move_joy(e.x * W, e.y * H)
                return True
        elif t == pygame.FINGERUP:
            act = self.press.pop(e.finger_id, None)
            if act:
                if act[0] == "joy":
                    self.joy_vec = (0.0, 0.0)
                    self.held = dict(left=False, right=False, up=False, down=False)
                return True
        return False

    def _move_joy(self, x, y):
        v = pygame.math.Vector2(x, y) - pygame.math.Vector2(self.joy_c)
        if v.length() > self.joy_r:
            v.scale_to_length(self.joy_r)
        self.joy_vec = (v.x / self.joy_r, -v.y / self.joy_r)
        d = 0.35
        self.held = dict(left=v.x < -d, right=v.x > d, up=v.y < -d, down=v.y > d)

    # ---------- integration -------------------------------------------------------------
    def override_held(self):
        return self.held if any(self.held.values()) else None

    def _prep(self):
        """pre-render every control once - drawing them each frame is then just a few small blits"""
        from full_game import font
        j = self.joy_r; k = self.knob_r
        self._joy = pygame.Surface((j * 2 + 8, j * 2 + 8), pygame.SRCALPHA)
        pygame.draw.circle(self._joy, (255, 255, 255, 40), (j + 4, j + 4), j)
        pygame.draw.circle(self._joy, (255, 255, 255, 90), (j + 4, j + 4), j, 5)
        self._knob = pygame.Surface((k * 2 + 4, k * 2 + 4), pygame.SRCALPHA)
        pygame.draw.circle(self._knob, (255, 220, 120, 170), (k + 2, k + 2), k)
        pygame.draw.circle(self._knob, (255, 255, 255, 120), (k + 2, k + 2), k, 4)
        self._btn = []
        for r, name, lab, col in self.buttons:
            c = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
            pygame.draw.circle(c, (*col, 150), (r.w // 2, r.h // 2), r.w // 2)
            pygame.draw.circle(c, (255, 255, 255, 120), (r.w // 2, r.h // 2), r.w // 2, 4)
            img = font(44 if len(lab) < 5 else 34).render(lab, True, (40, 20, 0))
            c.blit(img, img.get_rect(center=(r.w // 2, r.h // 2)))
            self._btn.append(c)
        self._pause_for = None

    def _prep_pause(self):
        from full_game import font
        r = self.pause_btn
        c = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
        pygame.draw.rect(c, (255, 255, 255, 60), c.get_rect(), border_radius=14)
        pygame.draw.rect(c, (255, 255, 255, 120), c.get_rect(), 3, border_radius=14)
        img = font(30).render(self.pause_label, True, (255, 255, 255))
        c.blit(img, img.get_rect(center=(r.w // 2, r.h // 2)))
        self._pause = c; self._pause_for = self.pause_label

    def draw(self, surf, alpha=140):
        if not self.active:
            return
        if not hasattr(self, "_joy"): self._prep()
        if self._pause_for != self.pause_label: self._prep_pause()
        x, y = self.joy_c
        surf.blit(self._joy, (x - self.joy_r - 4, y - self.joy_r - 4))
        kx = int(x + self.joy_vec[0] * (self.joy_r - self.knob_r))
        ky = int(y - self.joy_vec[1] * (self.joy_r - self.knob_r))
        surf.blit(self._knob, (kx - self.knob_r - 2, ky - self.knob_r - 2))
        for (r, name, lab, col), c in zip(self.buttons, self._btn):
            surf.blit(c, r.topleft)
        surf.blit(self._pause, self.pause_btn.topleft)
