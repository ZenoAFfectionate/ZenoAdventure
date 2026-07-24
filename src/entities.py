"""
entities.py - All game entities: Camera, Particle, Collectible, Enemy, Player,
MovingPlatform.

Collision model:
  * AABB (Axis-Aligned Bounding Box) with separate-axis resolution.
  * Solid tiles block movement on both axes.
  * One-way platforms only block when the entity is falling and its
    previous bottom edge was above the platform top.
  * Springs are solid; landing on one from above launches the entity upward.
"""

import math
import random
from dataclasses import dataclass

import pygame

from . import assets
from .constants import (
    TILE_SIZE, SCREEN_WIDTH, SCREEN_HEIGHT,
    GRAVITY, MAX_FALL_SPEED, JUMP_VELOCITY, JUMP_CUT_VELOCITY,
    PLAYER_FRICTION, PLAYER_MAX_SPEED,
    CLIMB_SPEED, COYOTE_TIME, JUMP_BUFFER, SPRING_VELOCITY,
    INVINCIBILITY_FRAMES, PLAYER_SCALE, ENEMY_SCALE, COLLECTIBLE_SCALE,
    STARTING_HEALTH, MAX_HEALTH,
    SKILL_NONE, SKILL_DASH, SKILL_DOUBLE_JUMP, SKILL_SLOW_MO,
    CHARACTER_SKILLS, STAR_INVINCIBILITY_FRAMES,
        WHITE, RED, GREEN, BLUE, YELLOW, GOLD, PURPLE, ORANGE,
)


# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------
class Camera:
    """Smooth-following camera clamped to level bounds."""

    def __init__(self, level_w: int, level_h: int):
        self.x = 0.0
        self.y = 0.0
        self.level_w = level_w
        self.level_h = level_h
        self.shake_timer = 0
        self.shake_intensity = 0

    def update(self, target_x: float, target_y: float):
        # Smooth lerp towards target
        tx = target_x - SCREEN_WIDTH / 2
        ty = target_y - SCREEN_HEIGHT / 2
        self.x += (tx - self.x) * 0.12
        self.y += (ty - self.y) * 0.12
        # Clamp
        self.x = max(0, min(self.x, self.level_w - SCREEN_WIDTH))
        self.y = max(0, min(self.y, self.level_h - SCREEN_HEIGHT))
        # Screen shake
        if self.shake_timer > 0:
            self.shake_timer -= 1

    def shake(self, intensity: int = 6, duration: int = 12):
        self.shake_intensity = intensity
        self.shake_timer = duration

    @property
    def offset(self) -> tuple[float, float]:
        ox = self.x
        oy = self.y
        if self.shake_timer > 0:
            ox += random.randint(-self.shake_intensity, self.shake_intensity)
            oy += random.randint(-self.shake_intensity, self.shake_intensity)
        return (ox, oy)

    def apply(self, rect: pygame.Rect) -> pygame.Rect:
        ox, oy = self.offset
        return rect.move(-ox, -oy)


# ---------------------------------------------------------------------------
# Particles
# ---------------------------------------------------------------------------
@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: int
    max_life: int
    color: tuple
    size: float
    gravity: float = 0.3

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.vy += self.gravity
        self.vx *= 0.96
        self.life -= 1

    @property
    def alive(self) -> bool:
        return self.life > 0

    def draw(self, surf: pygame.Surface, cam: Camera):
        ox, oy = cam.offset
        alpha = self.life / self.max_life
        r = max(1, int(self.size * alpha))
        a = int(255 * alpha)
        col = (self.color[0], self.color[1], self.color[2], a)
        # Reuse a tiny surface — cheaper than creating one each call
        s = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        pygame.draw.circle(s, col, (r, r), r)
        surf.blit(s, (int(self.x - ox - r), int(self.y - oy - r)))


class ParticleSystem:
    def __init__(self):
        self.particles: list[Particle] = []
        self.float_texts: list = []

    def emit_burst(self, x, y, color, count=12, speed=4, size=4, life=30, gravity=0.3):
        for _ in range(count):
            ang = random.uniform(0, math.tau)
            spd = random.uniform(speed * 0.3, speed)
            self.particles.append(Particle(
                x=x, y=y,
                vx=math.cos(ang) * spd,
                vy=math.sin(ang) * spd - 1,
                life=life,
                max_life=life,
                color=color,
                size=random.uniform(size * 0.6, size * 1.4),
                gravity=gravity,
            ))

    def emit_dust(self, x, y, count=6):
        for _ in range(count):
            self.particles.append(Particle(
                x=x + random.uniform(-8, 8),
                y=y,
                vx=random.uniform(-2, 2),
                vy=random.uniform(-2, -0.5),
                life=20,
                max_life=20,
                color=(200, 190, 170),
                size=random.uniform(2, 4),
                gravity=0.15,
            ))

    def emit_trail(self, x, y, color, count=3):
        for _ in range(count):
            self.particles.append(Particle(
                x=x + random.uniform(-4, 4),
                y=y + random.uniform(-4, 4),
                vx=random.uniform(-0.5, 0.5),
                vy=random.uniform(-0.5, 0.5),
                life=15,
                max_life=15,
                color=color,
                size=random.uniform(2, 5),
                gravity=0,
            ))

    def emit_float_text(self, x, y, text, color, life=45):
        self.float_texts.append({
            'x': x, 'y': y, 'text': text, 'color': color,
            'life': life, 'max_life': life, 'vy': -1.5,
        })

    def update(self):
        self.particles = [p for p in self.particles if p.alive]
        for p in self.particles:
            p.update()
        # Update floating texts
        for ft in self.float_texts:
            ft['y'] += ft['vy']
            ft['vy'] *= 0.95
            ft['life'] -= 1
        self.float_texts = [ft for ft in self.float_texts if ft['life'] > 0]

    def draw(self, surf, cam):
        for p in self.particles:
            p.draw(surf, cam)
        # Draw floating texts
        ox, oy = cam.offset
        for ft in self.float_texts:
            alpha = min(255, int(255 * ft['life'] / ft['max_life'] * 1.5))
            font = assets.get_font(18, bold=True)
            txt = font.render(ft['text'], True, ft['color'])
            txt.set_alpha(alpha)
            surf.blit(txt, (ft['x'] - ox - txt.get_width() // 2, ft['y'] - oy))


# ---------------------------------------------------------------------------
# Collectibles
# ---------------------------------------------------------------------------
COLLECTIBLE_DATA = {
    "o": {"sprite": "coin_bronze",      "score": 1,   "sound": "sfx_coin",   "color": (200, 140, 60)},
    "O": {"sprite": "coin_silver",      "score": 5,   "sound": "sfx_coin",   "color": (200, 200, 210)},
    "0": {"sprite": "coin_gold",        "score": 10,  "sound": "sfx_coin",   "color": GOLD},
    "b": {"sprite": "gem_blue",         "score": 20,  "sound": "sfx_gem",    "color": BLUE},
    "g": {"sprite": "gem_green",        "score": 20,  "sound": "sfx_gem",    "color": GREEN},
    "r": {"sprite": "gem_red",          "score": 20,  "sound": "sfx_gem",    "color": RED},
    "y": {"sprite": "gem_yellow",       "score": 20,  "sound": "sfx_gem",    "color": YELLOW},
    "H": {"sprite": "heart",            "score": 0,   "sound": "sfx_gem",    "color": RED, "heal": 1},
    "*": {"sprite": "star",             "score": 50,  "sound": "sfx_gem",    "color": GOLD},
    "c": {"sprite": "gem_blue",         "score": 15,  "sound": "sfx_gem",    "color": PURPLE},
}


class Collectible:

    def __init__(self, col: int, row: int, kind: str):
        self.col = col
        self.row = row
        self.kind = kind
        data = COLLECTIBLE_DATA[kind]
        self.sprite_name = data["sprite"]
        self.score = data["score"]
        self.sound_name = data.get("sound", "sfx_coin")
        self.heal = data.get("heal", 0)
        self.color = data["color"]

        surf = assets.get_tile(self.sprite_name)
        self.sprite = pygame.transform.smoothscale(
            surf, (int(surf.get_width() * COLLECTIBLE_SCALE), int(surf.get_height() * COLLECTIBLE_SCALE))
        )
        self.size = self.sprite.get_width()
        self.x = col * TILE_SIZE + (TILE_SIZE - self.size) / 2
        self.y = row * TILE_SIZE + (TILE_SIZE - self.size) / 2
        self.rect = pygame.Rect(self.x, self.y, self.size, self.size)
        self.collected = False
        self.bob = random.uniform(0, math.tau)
        self.spin = 0
        # Pre-generate 8 spin frames
        self._spin_frames = []
        for i in range(8):
            angle = i * math.pi / 8
            w = max(4, int(self.size * abs(math.cos(angle))))
            frame = pygame.transform.smoothscale(self.sprite, (w, self.size))
            self._spin_frames.append(frame)

    def update(self):
        self.bob += 0.06
        self.spin += 0.08

    @property
    def draw_y(self) -> float:
        return self.y + math.sin(self.bob) * 4

    @property
    def draw_rect(self) -> pygame.Rect:
        return pygame.Rect(self.x, self.draw_y, self.size, self.size)

    def draw(self, surf, cam):
        if self.collected:
            return
        # Use pre-cached spin frames
        idx = int(self.spin / (math.pi / 4)) % 8
        frame = self._spin_frames[idx]
        w = frame.get_width()
        ox, oy = cam.offset
        surf.blit(frame, (int(self.x + (self.size - w) / 2 - ox), int(self.draw_y - oy)))


# ---------------------------------------------------------------------------
# Moving Platform
# ---------------------------------------------------------------------------
class MovingPlatform:
    """A one-way platform that shuttles between two points.

    ``axis`` selects the movement direction: ``"x"`` moves right from the
    anchor tile, ``"y"`` moves up from it (the anchor is the lowest point).
    ``dx``/``dy`` expose the displacement applied by the latest update so a
    rider can be carried along; they are zero on frames where the platform
    is frozen (e.g. during the slow-mo skill).
    """

    def __init__(self, col: int, row: int, travel: int = 5, speed: float = 2.0,
                 axis: str = "x"):
        self.axis = axis
        self.start_x = col * TILE_SIZE
        self.start_y = row * TILE_SIZE
        self.x = float(self.start_x)
        self.y = float(self.start_y)
        self.min_x = self.start_x
        self.max_x = self.start_x + travel * TILE_SIZE
        self.min_y = self.start_y - travel * TILE_SIZE
        self.max_y = self.start_y
        self.speed = speed
        self.dir = 1 if axis == "x" else -1  # vertical platforms rise first
        self.dx = 0.0
        self.dy = 0.0
        self.width = TILE_SIZE
        self.height = TILE_SIZE // 2
        self.rect = pygame.Rect(int(self.x), int(self.y), self.width, self.height)
        self.sprite = assets.get_tile_scaled("block_planks", TILE_SIZE)

    def update(self, active: bool = True):
        """Advance the shuttle one frame; frozen platforms report no motion."""
        self.dx = 0.0
        self.dy = 0.0
        if not active:
            return
        if self.axis == "x":
            self.x += self.speed * self.dir
            if self.x >= self.max_x:
                self.x = self.max_x
                self.dir = -1
            elif self.x <= self.min_x:
                self.x = self.min_x
                self.dir = 1
            self.dx = self.x - self.rect.x
            self.rect.x = int(self.x)
        else:
            self.y += self.speed * self.dir
            if self.y >= self.max_y:
                self.y = self.max_y
                self.dir = -1
            elif self.y <= self.min_y:
                self.y = self.min_y
                self.dir = 1
            self.dy = self.y - self.rect.y
            self.rect.y = int(self.y)

    @property
    def vx(self) -> float:
        return self.dx

    def draw(self, surf, cam):
        ox, oy = cam.offset
        surf.blit(self.sprite, (self.rect.x - ox, self.rect.y - oy))


class FirePatch:
    """Short-lived hazard left by a stomped fire slime."""

    def __init__(self, x: float, ground_y: float, duration: int = 90, warning: int = 18):
        self.rect = pygame.Rect(int(x), int(ground_y - 22), TILE_SIZE, 22)
        self.timer = duration
        self.warning = warning
        self.sprite = assets.get_tile_scaled("fireball", 32)

    @property
    def dangerous(self) -> bool:
        return self.warning <= 0 and self.timer > 0

    @property
    def alive(self) -> bool:
        return self.timer > 0

    def update(self, slow_warning: bool = False):
        """Tick the patch.

        The burn timer always runs in real time; when ``slow_warning`` is
        set (Purple's time-slow) only the warning countdown is stretched, so
        players get more reaction time without extending the flame itself.
        """
        self.timer -= 1
        if self.warning > 0 and not slow_warning:
            self.warning -= 1

    def draw(self, surf, cam, frame: int):
        ox, oy = cam.offset
        color = ORANGE if self.dangerous else YELLOW
        alpha = 190 if self.dangerous else 80 + (frame % 12) * 8
        height = self.rect.height
        # Extinguish phase: the flame flickers and shrinks away so its end
        # is clearly readable instead of vanishing instantly.
        if self.dangerous and self.timer < 20:
            alpha = 90 + (frame % 6) * 20
            height = max(4, int(self.rect.height * self.timer / 20))
        glow = pygame.Surface((self.rect.w, height), pygame.SRCALPHA)
        glow.fill((*color, min(220, alpha)))
        surf.blit(glow, (self.rect.x - ox, self.rect.bottom - height - oy))
        if self.dangerous and self.timer >= 20:
            surf.blit(
                self.sprite,
                (self.rect.centerx - self.sprite.get_width() / 2 - ox,
                 self.rect.bottom - self.sprite.get_height() - oy),
            )


# ---------------------------------------------------------------------------
# Enemy
# ---------------------------------------------------------------------------
ENEMY_DATA = {
    "e": {"type": "slime",      "sprites": "slime",      "stompable": True,  "speed": 1.5},
    "q": {"type": "bee",        "sprites": "bee",        "stompable": True,  "speed": 2.0},
    "z": {"type": "saw",        "sprites": "saw",        "stompable": False, "speed": 0},
    "Z": {"type": "saw_track",  "sprites": "saw",        "stompable": False, "speed": 1.2},
    "f": {"type": "fish",       "sprites": "fish_blue",  "stompable": True,  "speed": 1.5},
    "w": {"type": "vfish",      "sprites": "fish_purple", "stompable": True, "speed": 1.2},
    "v": {"type": "fly",        "sprites": "fly",        "stompable": True,  "speed": 2.5},
    "n": {"type": "snail",      "sprites": "snail",      "stompable": True,  "speed": 0.8},
    "a": {"type": "fire_slime", "sprites": "slime_fire", "stompable": True,  "speed": 1.7},
    "s": {"type": "spike_slime","sprites": "slime_spike","stompable": False, "speed": 1.25,
          "dashable": True},
    "h": {"type": "frog",       "sprites": "frog",       "stompable": True,  "speed": 2.4},
}


class Enemy:
    def __init__(self, col: int, row: int, kind: str):
        self.col = col
        self.row = row
        self.kind = kind
        data = ENEMY_DATA[kind]
        self.etype = data["type"]
        self.stompable = data["stompable"]
        # Dash/star can destroy armoured-but-not-indestructible enemies
        # (spike slime yes, saws never).
        self.dashable = data.get("dashable", self.stompable)
        self.base_speed = data["speed"]
        self.sprites = assets.load_enemy_set(ENEMY_SCALE).get(data["sprites"], {})

        # Use first frame to determine size
        first = self.sprites.get("walk", self.sprites.get("fly", self.sprites.get("spin", [None])))[0]
        self.size = first.get_width() if first else TILE_SIZE
        self.x = col * TILE_SIZE + (TILE_SIZE - self.size) / 2
        self.y = row * TILE_SIZE + (TILE_SIZE - self.size) / 2
        self.start_x = self.x
        self.start_y = self.y

        self.vx = -self.base_speed if self.etype != "saw" else 0
        self.vy = 0.0
        self.dir = -1  # facing left initially
        self.alive = True
        self.dead_timer = 0

        # Hitbox (slightly smaller than sprite)
        pad = self.size * 0.15
        self.hitbox = pygame.Rect(
            self.x + pad, self.y + pad,
            self.size - pad * 2, self.size - pad * 2
        )

        # Animation
        self.anim_timer = 0
        self.anim_frame = 0

        # Type-specific patrol flavour:
        #   bee  — wide horizontal sweeps with a gentle bob
        #   fly  — tight horizontal range with tall vertical swoops
        self.fly_base_y = self.y
        self.fly_phase = random.uniform(0, math.tau)
        if self.etype == "bee":
            self.fly_amp = random.uniform(15, 25)
            self.patrol_range = 6 * TILE_SIZE
        elif self.etype == "fly":
            self.fly_amp = random.uniform(60, 90)
            self.patrol_range = 2 * TILE_SIZE
        else:
            self.fly_amp = random.uniform(30, 60)
            self.patrol_range = 6 * TILE_SIZE  # patrol distance

        # Saw track (moving saw): sinusoidal travel around the anchor
        self.track_len = 2 * TILE_SIZE
        self.track_phase = random.uniform(0, math.tau)

        # Kicked-shell bookkeeping (snail)
        self.kicked = False

        # Snail shell state
        self.in_shell = False
        self.shell_timer = 0

    def _anim_frames(self) -> list:
        if self.etype in ("slime", "fire_slime", "spike_slime"):
            return self.sprites.get("walk", self.sprites.get("rest", []))
        if self.etype == "bee":
            return self.sprites.get("fly", self.sprites.get("rest", []))
        if self.etype in ("saw", "saw_track"):
            return self.sprites.get("spin", self.sprites.get("rest", []))
        if self.etype in ("fish", "vfish"):
            return self.sprites.get("swim", self.sprites.get("rest", []))
        if self.etype == "fly":
            return self.sprites.get("fly", self.sprites.get("rest", []))
        if self.etype == "snail":
            if self.in_shell:
                return self.sprites.get("shell", self.sprites.get("rest", []))
            return self.sprites.get("walk", self.sprites.get("rest", []))
        if self.etype == "frog":
            if self.vy < -1:
                return self.sprites.get("jump", self.sprites.get("rest", []))
            return self.sprites.get("idle", self.sprites.get("rest", []))
        return self.sprites.get("rest", [])

    def _update_animation(self):
        self.anim_timer += 1
        frames = self._anim_frames()
        if len(frames) > 1 and self.anim_timer % 12 == 0:
            self.anim_frame = (self.anim_frame + 1) % len(frames)

    def update(self, tilemap):
        if not self.alive:
            self.dead_timer += 1
            return

        self._update_animation()

        if self.etype in ("slime", "snail", "fire_slime", "spike_slime"):
            self._update_walker(tilemap)
        elif self.etype == "frog":
            self._update_frog(tilemap)
        elif self.etype == "bee" or self.etype == "fly":
            self._update_flyer()
        elif self.etype == "saw":
            self._update_saw()
        elif self.etype == "saw_track":
            self._update_saw_track()
        elif self.etype == "fish":
            self._update_fish(tilemap)
        elif self.etype == "vfish":
            self._update_vfish(tilemap)

        # Update hitbox
        pad = self.size * 0.15
        self.hitbox.x = self.x + pad
        self.hitbox.y = self.y + pad

        # Snail shell recovery
        if self.in_shell:
            self.shell_timer -= 1
            if self.shell_timer <= 0:
                self.in_shell = False
                # Restore walking speed — vx decayed to ~0 during shell
                self.vx = -self.base_speed if self.dir < 0 else self.base_speed

    def _update_walker(self, tilemap):
        # ---- Gravity: keep walkers grounded ----
        self.vy += GRAVITY
        if self.vy > MAX_FALL_SPEED:
            self.vy = MAX_FALL_SPEED
        prev_bottom = self.y + self.size
        self.y += self.vy

        pad = self.size * 0.15
        # Full-height rect for ground detection — bottom extends to enemy's
        # feet (self.y + self.size) so collision is detected immediately on
        # contact, not pad-pixels late (which causes sinking & one-way tunneling).
        check_rect = pygame.Rect(
            self.x + pad, self.y,
            self.size - pad * 2, self.size
        )

        # Solid ground collision (landing on top of solid tiles)
        if self.vy > 0 and tilemap.rect_collides_solid(check_rect):
            tiles = tilemap.get_solid_tiles_in_rect(check_rect)
            min_top = min(t.top for t in tiles)
            self.y = min_top - self.size
            self.vy = 0
        # One-way platform collision (only when falling from above)
        elif self.vy >= 0:
            oneway_tiles = tilemap.get_oneway_tiles_in_rect(check_rect)
            for tile_rect in oneway_tiles:
                if prev_bottom <= tile_rect.top + 2:
                    self.y = tile_rect.top - self.size
                    self.vy = 0
                    break

        # ---- In-shell snail: decelerate, limited movement ----
        if self.in_shell:
            # Kicked shells travel further (gentler decay) but stay capped.
            decay = 0.96 if self.kicked else 0.8
            self.vx *= decay
            if abs(self.vx) < 0.05:
                self.vx = 0
                self.kicked = False
            else:
                self.x += self.vx
                # Wall collision for in-shell snail
                shell_rect = pygame.Rect(
                    self.x + pad, self.y + pad,
                    self.size - pad * 2, self.size - pad * 2
                )
                if tilemap.rect_collides_solid(shell_rect):
                    self.x -= self.vx
                    self.vx = -self.vx
            self.hitbox.x = self.x + pad
            self.hitbox.y = self.y + pad
            return

        # ---- Horizontal movement ----
        self.x += self.vx
        new_hitbox = pygame.Rect(
            self.x + pad, self.y + pad,
            self.size - pad * 2, self.size - pad * 2
        )

        # Turn at walls
        if tilemap.rect_collides_solid(new_hitbox):
            self.x -= self.vx
            self.vx = -self.vx
            self.dir = -self.dir

        # Turn at edges (check if there's ground ahead of the leading foot)
        # When moving right, check near the right edge of the sprite
        # When moving left, check near the left edge of the sprite
        turn = False
        if self.vx > 0:
            ahead_x = self.x + self.size * 0.85
        else:
            ahead_x = self.x + self.size * 0.15
        foot_y = self.y + self.size
        check_col = int(ahead_x // TILE_SIZE)
        check_row = int(foot_y // TILE_SIZE)
        # Check for ground at the SAME level as the current platform only.
        # Using max_depth=1 prevents walkers from walking off high platforms
        # just because there's ground far below.
        has_ground = tilemap.has_ground_below(check_col, check_row, max_depth=1)
        if not has_ground:
            turn = True

        # Clamp patrol range
        if abs(self.x - self.start_x) > self.patrol_range:
            turn = True

        # Only flip once even if both conditions are true (avoids double-flip
        # cancel-out where enemy walks off the edge at patrol boundary)
        if turn:
            self.vx = -self.vx
            self.dir = -self.dir

    def _update_flyer(self):
        self.x += self.vx
        self.fly_phase += 0.04
        self.y = self.fly_base_y + math.sin(self.fly_phase) * self.fly_amp
        # Turn at patrol range
        if self.x > self.start_x + self.patrol_range:
            self.vx = -abs(self.vx)
            self.dir = -1
        elif self.x < self.start_x - self.patrol_range:
            self.vx = abs(self.vx)
            self.dir = 1

    def _update_saw(self):
        # Stationary rotating saw
        pass

    def _update_saw_track(self):
        """Saw gliding along a short horizontal track (endpoints previewed).

        Sinusoidal motion keeps it predictable: players read the track and
        time their crossing.
        """
        self.track_phase += self.base_speed * 0.02
        self.x = self.start_x + math.sin(self.track_phase) * self.track_len
        self.dir = 1 if math.cos(self.track_phase) >= 0 else -1

    def _update_vfish(self, tilemap):
        """Vertical fish: patrols its water column up and down."""
        col = int((self.x + self.size / 2) // TILE_SIZE)
        water_rows = [row for water_col, row in tilemap.water if water_col == col]
        if not water_rows:
            return  # never swim out of water
        top = min(water_rows) * TILE_SIZE
        bottom = (max(water_rows) + 1) * TILE_SIZE - self.size
        self.fly_phase += self.base_speed * 0.02
        center = (top + bottom) / 2
        amp = max(0.0, (bottom - top) / 2 - 4)
        self.y = center + math.sin(self.fly_phase) * amp
        self.dir = 1 if math.cos(self.fly_phase) >= 0 else -1
        # Gentle horizontal sway, clamped inside the water column
        self.x = self.start_x + math.sin(self.fly_phase * 0.5) * 10

    def _update_frog(self, tilemap):
        """Pause, then leap in a readable arc so players can anticipate it."""
        if not hasattr(self, "jump_wait"):
            self.jump_wait = 50
        self.vy = min(MAX_FALL_SPEED, self.vy + GRAVITY)
        prev_bottom = self.y + self.size
        self.y += self.vy
        pad = self.size * 0.15
        body = pygame.Rect(self.x + pad, self.y, self.size - pad * 2, self.size)
        landed = False
        if self.vy >= 0 and tilemap.rect_collides_solid(body):
            tiles = tilemap.get_solid_tiles_in_rect(body)
            self.y = min(t.top for t in tiles) - self.size
            self.vy = 0
            landed = True
        elif self.vy >= 0:
            for tile in tilemap.get_oneway_tiles_in_rect(body):
                if prev_bottom <= tile.top + 2:
                    self.y = tile.top - self.size
                    self.vy = 0
                    landed = True
                    break
        if landed:
            self.jump_wait -= 1
            if self.jump_wait <= 0:
                self.vy = -11.5
                self.vx = self.dir * self.base_speed
                self.jump_wait = 65
        else:
            self.x += self.vx
        if abs(self.x - self.start_x) > self.patrol_range:
            self.dir *= -1
            self.vx = self.dir * self.base_speed

    def _update_fish(self, tilemap):
        self.fly_phase += 0.03
        col = int((self.x + self.size / 2) // TILE_SIZE)
        water_rows = [row for water_col, row in tilemap.water if water_col == col]
        target_y = self.fly_base_y + math.sin(self.fly_phase) * 20
        if water_rows:
            top = min(water_rows) * TILE_SIZE
            bottom = (max(water_rows) + 1) * TILE_SIZE - self.size
            self.y = max(top, min(target_y, bottom))
        else:
            self.y = target_y

        next_x = self.x + self.vx
        next_col = int((next_x + self.size / 2) // TILE_SIZE)
        next_row = int((self.y + self.size / 2) // TILE_SIZE)
        if (next_col, next_row) not in tilemap.water:
            self.vx = -self.vx
            self.dir = -self.dir
        else:
            self.x = next_x
        if self.x > self.start_x + self.patrol_range:
            self.vx = -abs(self.vx)
            self.dir = -1
        elif self.x < self.start_x - self.patrol_range:
            self.vx = abs(self.vx)
            self.dir = 1

    def stomp(self):
        """Called when the player stomps this enemy from above."""
        if not self.stompable:
            return False
        if self.etype == "snail":
            if not self.in_shell:
                self.in_shell = True
                self.shell_timer = 180  # 3 seconds in shell
                self.vx *= 0.3
                self.kicked = False
                return True  # bounced but not killed
            else:
                self.alive = False
                return True
        self.alive = False
        return True

    def kick(self, direction: int) -> bool:
        """Kick a stationary shelled snail; speed capped, chain hits limited."""
        if self.etype == "snail" and self.in_shell and abs(self.vx) < 1.5:
            self.vx = (1 if direction > 0 else -1) * 6.0
            self.kicked = True
            return True
        return False

    def kill(self):
        self.alive = False

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.size, self.size)

    def _get_frame(self):
        """Get current animation frame, flipped if needed (cached)."""
        frames = self._anim_frames()
        if not frames:
            return None
        frame = frames[self.anim_frame % len(frames)]
        if self.dir < 0:
            # Cache flipped frames
            cache_key = id(frame)
            if not hasattr(self, '_flip_cache'):
                self._flip_cache = {}
            if cache_key not in self._flip_cache:
                self._flip_cache[cache_key] = pygame.transform.flip(frame, True, False)
            frame = self._flip_cache[cache_key]
        return frame

    def draw(self, surf, cam):
        if not self.alive and self.dead_timer > 20:
            return
        frame = self._get_frame()
        if frame is None:
            return
        ox, oy = cam.offset

        if not self.alive:
            # Squish effect
            t = self.dead_timer / 20
            h = max(4, int(self.size * (1 - t)))
            frame = pygame.transform.smoothscale(frame, (self.size, h))
            surf.blit(frame, (int(self.x - ox), int(self.y + (self.size - h) - oy)))
            return

        # Saw track: preview the travel path so the hazard is readable.
        if self.etype == "saw_track":
            y = int(self.y + self.size / 2 - oy)
            x0 = int(self.start_x - self.track_len + self.size / 2 - ox)
            x1 = int(self.start_x + self.track_len + self.size / 2 - ox)
            track_col = (150, 150, 160)
            pygame.draw.line(surf, track_col, (x0, y), (x1, y), 2)
            pygame.draw.circle(surf, track_col, (x0, y), 4)
            pygame.draw.circle(surf, track_col, (x1, y), 4)

        # Frog: telegraphed leap — landing shadow grows as takeoff nears,
        # and the body squashes just before the jump.
        if self.etype == "frog" and self.vy == 0:
            wait = getattr(self, "jump_wait", 99)
            if wait < 25:
                flight = 2 * 11.5 / GRAVITY
                dx = self.dir * self.base_speed * flight
                offset = (self.x + dx) - self.start_x
                offset = max(-self.patrol_range, min(self.patrol_range, offset))
                lx = self.start_x + offset + self.size / 2
                ground_y = int(self.y + self.size - 4 - oy)
                alpha = min(110, 30 + (25 - wait) * 5)
                shadow = pygame.Surface((36, 10), pygame.SRCALPHA)
                pygame.draw.ellipse(shadow, (20, 20, 30, alpha), shadow.get_rect())
                surf.blit(shadow, (int(lx - 18 - ox), ground_y))
            if wait < 10:
                frame = pygame.transform.smoothscale(
                    frame, (self.size, max(4, int(self.size * 0.85)))
                )
                surf.blit(frame, (int(self.x - ox),
                                  int(self.y + self.size - frame.get_height() - oy)))
                return

        surf.blit(frame, (int(self.x - ox), int(self.y - oy)))


# ---------------------------------------------------------------------------
# Player
# ---------------------------------------------------------------------------
class Player:
    # States
    IDLE = "idle"
    WALK = "walk"
    JUMP = "jump"
    DUCK = "duck"
    CLIMB = "climb"
    HIT = "hit"

    def __init__(self, x: float, y: float, color: str = "beige"):
        self.color = color
        self.frames = assets.load_character_set(color, PLAYER_SCALE)
        self.sprite_w = self.frames["idle"][0].get_width()
        self.sprite_h = self.frames["idle"][0].get_height()

        # Skill info (needed early for max_health and passive traits)
        from .constants import CHARACTER_SKILLS
        self._skill_info = CHARACTER_SKILLS.get(color, {})

        # Hitbox (narrower than sprite for tight platforming)
        self.stand_w = 38
        self.stand_h = 58
        self.duck_w = 38
        self.duck_h = 34

        self.x = x
        self.y = y
        self.vx = 0.0
        self.vy = 0.0
        self.facing = 1  # 1 = right, -1 = left
        self.state = self.IDLE
        self.on_ground = False
        self.on_ladder = False
        self.climbing = False
        self.ducking = False

        # Hitbox (positioned so feet are at y + h)
        self.w = self.stand_w
        self.h = self.stand_h
        self.rect = pygame.Rect(0, 0, self.w, self.h)
        self._sync_rect()

        # Health
        self.max_health = self._skill_info.get("max_health", MAX_HEALTH)
        self.health = STARTING_HEALTH
        self.lives = 3
        self.invincible = 0

        # Jump mechanics
        self.coyote = 0
        self.jump_buffer = 0
        self.jumping = False

        # Previous state (for stomp detection)
        self.prev_feet_y = 0.0

        # Animation
        self.anim_timer = 0
        self.anim_frame = 0

        # Score
        self.score = 0
        self.coins = 0
        self.gems = 0

        # Spring bounce flag
        self.spring_bounce = False

        # Footstep dust timer
        self.dust_timer = 0

        # Previous velocity (for landing detection)
        self.prev_vy = 0.0

        # Flipped frame cache
        self._flip_cache: dict = {}

        # ---- Skill system ----
        self.skill_type = self._skill_info.get("skill", SKILL_NONE)
        self.skill_cooldown = 0       # frames remaining on cooldown
        self.skill_active = False     # is skill currently active?
        self.skill_timer = 0          # frames remaining for active skill
        self.dash_vx = 0.0

        # Double jump
        self.double_jumps_left = 1

        # Star power-up invincibility
        self.star_invincible = 0

        # Moving platform the player is currently standing on (if any)
        self.riding: MovingPlatform | None = None

    def _sync_rect(self):
        """Position the hitbox centered on x, with bottom at y + h."""
        self.rect.x = int(self.x - self.w / 2)
        self.rect.y = int(self.y)
        self.rect.w = self.w
        self.rect.h = self.h

    @property
    def center_x(self) -> float:
        return self.x

    @property
    def center_y(self) -> float:
        return self.y + self.h / 2

    @property
    def feet_y(self) -> float:
        return self.y + self.h

    def reset(self, x: float, y: float):
        self.x = x
        self.y = y
        self.vx = 0
        self.vy = 0
        self.state = self.IDLE
        self.on_ground = False
        self.climbing = False
        self.ducking = False
        self.w = self.stand_w
        self.h = self.stand_h
        self.invincible = 0
        self.coyote = 0
        self.jump_buffer = 0
        self.jumping = False
        self.prev_feet_y = 0.0
        self._sync_rect()
        # Reset skill state
        self.skill_cooldown = 0
        self.skill_active = False
        self.skill_timer = 0
        self.dash_vx = 0.0
        self.double_jumps_left = 1
        self.star_invincible = 0
        self.riding = None

    def take_damage(self, ignore_star: bool = False) -> bool:
        """Returns True if damage was actually taken."""
        if self.invincible > 0 or (self.star_invincible > 0 and not ignore_star):
            return False
        self.health -= 1
        iframes_mult = self._skill_info.get("passive_iframes_mult", 1.0)
        self.invincible = int(INVINCIBILITY_FRAMES * iframes_mult)
        self.state = self.HIT
        self.vy = -8  # knockback up
        return True

    def take_hazard_hit(self, particles, sound_fn) -> bool:
        """Consume star protection or take ordinary terrain damage."""
        if self.invincible > 0:
            return False
        if self.star_invincible > 0:
            self.star_invincible = 0
            self.invincible = 30
            self.vy = -8
            sound_fn("sfx_hurt")
            particles.emit_burst(
                self.center_x, self.center_y, RED,
                count=12, speed=4, size=4, life=24,
            )
            return True
        if self.take_damage():
            sound_fn("sfx_hurt")
            return True
        return False

    def update(self, keys, tilemap, particles, sound_fn):
        if self.invincible > 0:
            self.invincible -= 1
        if self.star_invincible > 0:
            self.star_invincible -= 1

        # ---- Skill cooldown tick ----
        if self.skill_cooldown > 0:
            self.skill_cooldown -= 1

        # ---- Dash active override ----
        if self.skill_active and self.skill_type == SKILL_DASH:
            self.vx = self.dash_vx
            self.vy = 0  # no gravity during dash
            self.skill_timer -= 1
            # Trail particles
            particles.emit_trail(self.x, self.center_y, GREEN, count=2)
            if self.skill_timer <= 0:
                self.skill_active = False
                self.dash_vx = 0.0

        # ---- Determine input ----
        left = keys[pygame.K_LEFT] or keys[pygame.K_a]
        right = keys[pygame.K_RIGHT] or keys[pygame.K_d]
        down = keys[pygame.K_DOWN] or keys[pygame.K_s]
        up = keys[pygame.K_UP] or keys[pygame.K_w]
        jump_held = keys[pygame.K_SPACE] or keys[pygame.K_z] or keys[pygame.K_j]

        # ---- Ladder check ----
        center_col = int(self.center_x // TILE_SIZE)
        feet_row = int((self.y + self.h * 0.5) // TILE_SIZE)
        self.on_ladder = tilemap.is_ladder_at(center_col, feet_row) or \
                         tilemap.is_ladder_at(center_col, int(self.feet_y // TILE_SIZE))

        # ---- Climbing ----
        if self.on_ladder and (up or down) and not self.ducking:
            self.climbing = True
        if self.climbing:
            if not self.on_ladder:
                self.climbing = False
            else:
                if up:
                    self.vy = -CLIMB_SPEED
                elif down:
                    self.vy = CLIMB_SPEED
                else:
                    self.vy = 0
                self.state = self.CLIMB
                # Horizontal control on ladder
                if left:
                    self.x -= 2
                    self.facing = -1
                if right:
                    self.x += 2
                    self.facing = 1

        # ---- Ducking ----
        if not self.climbing:
            if down and self.on_ground:
                if not self.ducking:
                    # Adjust y so feet stay at the same position when shrinking
                    self.y += self.h - self.duck_h
                    self.ducking = True
                    self.w = self.duck_w
                    self.h = self.duck_h
            else:
                # Can't unduck if ceiling too low
                if self.ducking:
                    # Check the space where the standing hitbox would be
                    # (feet stay put, so top moves up by stand_h - duck_h)
                    stand_y = self.y + self.h - self.stand_h
                    # Shrink height by 1px so the rect bottom doesn't touch
                    # the ground tile below (which would cause a false
                    # collision and prevent unducking).
                    unduck_rect = pygame.Rect(
                        int(self.x - self.stand_w / 2), int(stand_y),
                        self.stand_w, self.stand_h - 1
                    )
                    if not tilemap.rect_collides_solid(unduck_rect):
                        # Adjust y so feet stay at the same position when growing
                        self.y = stand_y
                        self.ducking = False
                        self.w = self.stand_w
                        self.h = self.stand_h
                if not self.ducking:
                    self.w = self.stand_w
                    self.h = self.stand_h

        # ---- Horizontal movement ----
        if not self.climbing and not self.ducking and not self.skill_active:
            speed_mult = self._skill_info.get("passive_speed_mult", 1.0)
            max_speed = PLAYER_MAX_SPEED * speed_mult
            target = 0
            if left:
                target -= max_speed
                self.facing = -1
            if right:
                target += max_speed
                self.facing = 1

            if target != 0:
                # Faster acceleration on ground, slower in air for control
                accel = 0.25 if self.on_ground else 0.15
                self.vx += (target - self.vx) * accel
                if abs(self.vx) < 0.1:
                    self.vx = target
            else:
                # Friction: strong on ground, weak in air
                fric = PLAYER_FRICTION if self.on_ground else 0.95
                self.vx *= fric
                if abs(self.vx) < 0.1:
                    self.vx = 0
        elif self.ducking:
            self.vx *= 0.7
        elif self.climbing:
            self.vx *= 0.5

        # ---- Jump (with coyote time + buffer) ----
        if self.on_ground:
            self.coyote = COYOTE_TIME
        else:
            if self.coyote > 0:
                self.coyote -= 1

        # Jump buffer: consume buffered jump when landing
        if self.jump_buffer > 0:
            self.jump_buffer -= 1
            if self.coyote > 0:
                self.vy = JUMP_VELOCITY
                self.coyote = 0
                self.jumping = True
                self.jump_buffer = 0
                sound_fn("sfx_jump-high" if abs(self.vx) > 3 else "sfx_jump")

        # Variable jump height: if jump released early, cut velocity
        if self.jumping and not jump_held and self.vy < JUMP_CUT_VELOCITY:
            self.vy = JUMP_CUT_VELOCITY
            self.jumping = False

        # ---- Gravity ----
        if not self.climbing and not self.skill_active:
            self.vy += GRAVITY
            if self.vy > MAX_FALL_SPEED:
                self.vy = MAX_FALL_SPEED

        # ---- Riding a moving platform ----
        # Glue the rider to the platform's latest displacement so vertical
        # shuttles carry the player smoothly instead of relying on repeated
        # fall-and-land catches (which jitter).
        if self.riding is not None:
            mp = self.riding
            still_on = (
                self.on_ground
                and self.rect.right > mp.rect.left - 2
                and self.rect.left < mp.rect.right + 2
            )
            if still_on:
                old_x, old_y = self.x, self.y
                self.x += mp.dx
                self.y += mp.dy
                self._sync_rect()
                self._collide_x(tilemap)
                if tilemap.rect_collides_solid(self.rect):
                    # Never let a platform push the player into geometry.
                    self.x, self.y = old_x, old_y
                    self._sync_rect()
                    self.riding = None
            else:
                self.riding = None

        # ---- Move X ----
        self.x += self.vx
        self._sync_rect()
        self._collide_x(tilemap)

        # ---- Move Y ----
        prev_feet = self.feet_y
        self.prev_feet_y = prev_feet
        self.y += self.vy
        self._sync_rect()
        landed = self._collide_y(tilemap, prev_feet, particles, sound_fn)

        # Belts only influence a grounded player and remain weak enough to
        # counter-steer, creating timing pressure without removing control.
        if landed:
            belt_dir = tilemap.conveyor_at_feet(self.rect)
            if belt_dir:
                belt_mult = getattr(tilemap, "conveyor_speed_mult", 1.0)
                self.x += belt_dir * 2.2 * belt_mult
                self._sync_rect()
                self._collide_x(tilemap)

        # ---- Spring check ----
        self._check_springs(tilemap, sound_fn)

        # ---- Hazard check ----
        if tilemap.rect_collides_hazard(self.rect):
            if self.take_hazard_hit(particles, sound_fn):
                self.vx *= -0.5  # bounce back from hazard

        # ---- Water check ----
        in_water = tilemap.rect_collides_water(self.rect)
        if in_water:
            self.vy *= 0.6
            if self.vy > 3:
                self.vy = 3

        # ---- State determination ----
        if self.state != self.HIT or self.invincible == 0:
            if self.climbing:
                self.state = self.CLIMB
            elif self.ducking:
                self.state = self.DUCK
            elif not self.on_ground:
                self.state = self.JUMP
            elif abs(self.vx) > 0.5:
                self.state = self.WALK
            else:
                self.state = self.IDLE

        # Clear hit state after a while
        if self.state == self.HIT and self.invincible < INVINCIBILITY_FRAMES - 30:
            self.state = self.IDLE

        # ---- Animation ----
        self._update_animation()

        # ---- Footstep dust ----
        if self.on_ground and abs(self.vx) > 2:
            self.dust_timer += 1
            if self.dust_timer > 10:
                self.dust_timer = 0
                particles.emit_dust(self.x, self.feet_y)

    def try_jump(self, tilemap, sound_fn):
        """Called on jump key press (event-driven)."""
        if self.climbing:
            self.climbing = False
            self.vy = JUMP_VELOCITY
            self.jumping = True
            self.jump_buffer = 0
            self.riding = None
            sound_fn("sfx_jump")
            return
        if self.coyote > 0:
            mult = self._skill_info.get("jump_vel_mult", 1.0)
            self.vy = JUMP_VELOCITY * mult
            self.coyote = 0
            self.on_ground = False
            self.jumping = True
            self.jump_buffer = 0
            self.riding = None
            sound_fn("sfx_jump-high" if abs(self.vx) > 3 else "sfx_jump")
        elif self.skill_type == SKILL_DOUBLE_JUMP and self.double_jumps_left > 0:
            # Double jump
            self.vy = JUMP_VELOCITY * 0.85
            self.jumping = True
            self.double_jumps_left -= 1
            self.riding = None
            sound_fn("sfx_jump-high")
        else:
            # Buffer the jump press for later (when player lands)
            self.jump_buffer = JUMP_BUFFER

    def _collide_x(self, tilemap):
        # Use a slightly shorter rect (shrink top+bottom by 2px) so that
        # ground/ceiling tiles don't trigger false horizontal collisions.
        check_rect = pygame.Rect(
            self.rect.x, self.rect.y + 2, self.rect.w, self.rect.h - 4
        )
        if tilemap.rect_collides_solid(check_rect):
            tiles = tilemap.get_solid_tiles_in_rect(check_rect)
            for tile_rect in tiles:
                if self.vx > 0:
                    self.x = tile_rect.left - self.w / 2
                elif self.vx < 0:
                    self.x = tile_rect.right + self.w / 2
                self.vx = 0
                self._sync_rect()
                break

        # Final safety clamp for high-speed movement such as dash or
        # knockback. The virtual wall resolves normal movement, while this
        # guarantees that even a one-frame overshoot cannot leave the map.
        min_x = self.w / 2
        max_x = tilemap.pixel_w - self.w / 2
        clamped_x = max(min_x, min(self.x, max_x))
        if clamped_x != self.x:
            self.x = clamped_x
            self.vx = 0
            self._sync_rect()

    def _collide_y(self, tilemap, prev_feet, particles, sound_fn) -> bool:
        landed = False
        solid_hit = False

        # Solid tiles
        if tilemap.rect_collides_solid(self.rect):
            # The broad-phase query includes virtual side-wall columns. They
            # belong to horizontal resolution only; treating them as floors
            # or ceilings can launch the player vertically at a map edge.
            tiles = [
                tile for tile in tilemap.get_solid_tiles_in_rect(self.rect)
                if 0 <= tile.left < tilemap.pixel_w
            ]
            for tile_rect in tiles:
                if self.vy > 0:
                    self.y = tile_rect.top - self.h
                    landed = True
                elif self.vy < 0:
                    self.y = tile_rect.bottom
                self.vy = 0
                self._sync_rect()
                solid_hit = True
                break

        # One-way platforms (only when falling)
        if not solid_hit and self.vy >= 0:
            oneway_tiles = tilemap.get_oneway_tiles_in_rect(self.rect)
            for tile_rect in oneway_tiles:
                if prev_feet <= tile_rect.top + 2:
                    self.y = tile_rect.top - self.h
                    self.vy = 0
                    landed = True
                    self._sync_rect()
                    break

        # Moving platforms (one-way)
        if not solid_hit and self.vy >= 0:
            for mp in tilemap.moving_platforms:
                if self.rect.colliderect(mp.rect):
                    if prev_feet <= mp.rect.top + 4:
                        self.y = mp.rect.top - self.h
                        self.vy = 0
                        landed = True
                        self.riding = mp
                        # Move with platform
                        self.x += mp.dx
                        self._sync_rect()
                        break

        if landed:
            was_air = not self.on_ground
            self.on_ground = True
            self.spring_bounce = False  # Reset spring bounce on landing
            self.double_jumps_left = 1  # Reset double jump on landing
            if was_air and self.vy == 0 and abs(self.prev_vy) > 6:
                particles.emit_dust(self.x, self.feet_y)
                sound_fn("sfx_bump")
        else:
            self.on_ground = False

        self.prev_vy = self.vy
        return landed

    def _check_springs(self, tilemap, sound_fn):
        spring_tiles = tilemap.get_spring_tiles_in_rect(self.rect)
        for tile_rect in spring_tiles:
            if self.vy >= 0 and self.feet_y < tile_rect.top + 16:
                self.vy = SPRING_VELOCITY
                self.jumping = False  # Don't let variable-jump cut the spring bounce
                self.on_ground = False
                self.spring_bounce = True
                sound_fn("sfx_magic")
                # Activate spring animation
                col = tile_rect.x // TILE_SIZE
                row = tile_rect.y // TILE_SIZE
                tilemap.spring_timers[(col, row)] = 12

    # -----------------------------------------------------------------
    # Skill system
    # -----------------------------------------------------------------
    def try_skill(self, game, tilemap, enemies, particles, sound_fn):
        """Unified skill trigger entry point. Returns True if skill was activated."""
        if self.skill_cooldown > 0 or self.skill_active:
            return False
        if self.skill_type == SKILL_DASH:
            self._activate_dash(particles, sound_fn)
            return True
        elif self.skill_type == SKILL_SLOW_MO:
            self._activate_slow_mo(game, particles, sound_fn)
            return True
        # Double jump is handled in try_jump, not here
        return False

    def _activate_dash(self, particles, sound_fn):
        """Activate the dash skill: quick horizontal burst, invincible during dash."""
        info = self._skill_info
        self.skill_active = True
        self.skill_timer = info.get("duration", 15)
        self.dash_vx = self.facing * info.get("dash_speed", 18.0)
        self.invincible = max(self.invincible, info.get("duration", 15))
        self.skill_cooldown = info.get("cooldown", 720)
        self.on_ground = False
        self.jumping = False
        sound_fn("sfx_throw")
        particles.emit_burst(
            self.x, self.center_y, GREEN,
            count=12, speed=5, size=4, life=20
        )

    def _activate_slow_mo(self, game, particles, sound_fn):
        """Activate the slow-mo skill: slows enemies for a duration."""
        info = self._skill_info
        self.skill_active = True
        self.skill_timer = info.get("duration", 180)
        self.skill_cooldown = info.get("cooldown", 900)
        if hasattr(game, 'slow_mo_timer'):
            game.slow_mo_timer = info.get("duration", 180)
        sound_fn("sfx_magic")
        particles.emit_burst(
            self.x, self.center_y, (160, 80, 220),
            count=20, speed=4, size=5, life=30
        )

    def update_skill(self, tilemap, enemies, particles, sound_fn, defeat_fn=None):
        """Update skill state each frame. Called at end of update().
        Handles dash enemy-killing and slow-mo timer expiry."""
        if self.skill_active and self.skill_type == SKILL_SLOW_MO:
            # Slow-mo just needs timer expiry (handled in update)
            if self.skill_timer <= 0:
                self.skill_active = False
        elif self.skill_active and self.skill_type == SKILL_DASH:
            # Kill enemies in dash path (dashable: incl. spike slimes)
            for enemy in enemies:
                if not enemy.alive:
                    continue
                if self.rect.colliderect(enemy.hitbox) and enemy.dashable:
                    enemy.kill()
                    if defeat_fn:
                        defeat_fn(enemy, "dash")
                    else:
                        particles.emit_burst(
                            enemy.x + enemy.size / 2,
                            enemy.y + enemy.size / 2,
                            WHITE, count=14, speed=4, size=4, life=25
                        )
                        sound_fn("sfx_disappear")

    def activate_star(self, particles, sound_fn):
        """Activate star invincibility power-up."""
        self.star_invincible = STAR_INVINCIBILITY_FRAMES
        sound_fn("sfx_magic")
        particles.emit_burst(
            self.x, self.center_y, GOLD,
            count=20, speed=5, size=5, life=35
        )

    def reset_skill_cooldown(self):
        """Reset skill cooldown (used by charge crystals)."""
        self.skill_cooldown = 0

    def _update_animation(self):
        self.anim_timer += 1
        state = self.state
        frames = self.frames.get(state, self.frames["idle"])
        if not frames:
            frames = self.frames["idle"]

        anim_speed = 8 if state == self.WALK else 12 if state == self.CLIMB else 999
        if len(frames) > 1 and self.anim_timer % anim_speed == 0:
            self.anim_frame = (self.anim_frame + 1) % len(frames)
        elif len(frames) <= 1:
            self.anim_frame = 0

    def draw(self, surf, cam):
        # Flash during invincibility
        if self.invincible > 0 and self.invincible % 6 < 3:
            return

        state = self.state
        frames = self.frames.get(state, self.frames["idle"])
        if not frames:
            frames = self.frames["idle"]
        frame = frames[self.anim_frame % len(frames)]

        if self.facing < 0:
            # Use cached flip if available
            cache_key = id(frame)
            if cache_key not in self._flip_cache:
                self._flip_cache[cache_key] = pygame.transform.flip(frame, True, False)
            frame = self._flip_cache[cache_key]

        ox, oy = cam.offset
        # Center sprite horizontally on hitbox, align bottom
        draw_x = self.rect.centerx - frame.get_width() / 2 - ox
        draw_y = self.rect.bottom - frame.get_height() - oy + 2
        surf.blit(frame, (int(draw_x), int(draw_y)))


# ---------------------------------------------------------------------------
# Mini-boss: Block Guardian
# ---------------------------------------------------------------------------
class ShockWave:
    """Ground-hugging wave the guardian emits on landing.  Jumpable."""

    SPEED = 4.5
    HEIGHT = 18
    WIDTH = 14

    def __init__(self, x: float, floor_top: float, direction: int, max_travel: float):
        self.x = x
        self.y = floor_top - self.HEIGHT
        self.dir = direction
        self.travel_left = max_travel

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x - self.WIDTH / 2), int(self.y),
                           self.WIDTH, self.HEIGHT)

    @property
    def alive(self) -> bool:
        return self.travel_left > 0

    def update(self):
        self.x += self.dir * self.SPEED
        self.travel_left -= self.SPEED

    def draw(self, surf, cam, frame: int):
        ox, oy = cam.offset
        r = self.rect
        flick = 160 + (frame % 8) * 10
        wave = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
        wave.fill((240, 170, 60, min(230, flick)))
        surf.blit(wave, (r.x - ox, r.y - oy))


class BlockGuardian:
    """Three-phase mini-boss guarding the Sky Temple exit.

    Cycle: WARNING (0.75 s landing marker) -> FALLING (drops from the sky)
    -> CHARGE (0.25 s flash) -> SHOCKWAVE (two jumpable ground waves)
    -> VULNERABLE (2.5 s stomp window).  Three stomps win and open the door.

    Fair-play rules: the guardian only wakes once the player has landed
    inside the arena, it only hurts with telegraphed attacks (the fall and
    the shockwaves), and it is harmless to touch while VULNERABLE, so every
    character can win without taking damage.  Skills never skip the fight;
    slow-mo stretches every timer; pausing freezes the boss because
    update() simply isn't called then.
    """

    HIDDEN = "hidden"
    WARNING = "warning"
    FALLING = "falling"
    CHARGE = "charge"
    SHOCKWAVE = "shockwave"
    VULNERABLE = "vulnerable"
    SQUASHED = "squashed"
    DEFEATED = "defeated"

    WARNING_TIME = 45       # >= 0.5 s readable telegraph (0.75 s)
    CHARGE_TIME = 15        # extra tell before the shockwave fires
    VULNERABLE_TIME = 150   # 2.5 s stomp window
    SQUASHED_TIME = 25
    MAX_HITS = 3

    def __init__(self, col: int, row: int, arena_left: float, arena_right: float):
        self.size = TILE_SIZE
        self.arena_left = arena_left
        self.arena_right = arena_right
        self.floor_top = (row + 1) * TILE_SIZE
        self.anchor_x = col * TILE_SIZE
        self.trigger_x = arena_left - TILE_SIZE  # wakes as the player enters

        def sprite(name: str) -> pygame.Surface:
            return pygame.transform.smoothscale(
                assets.get_enemy(name), (self.size, self.size))

        self.sprite_idle = sprite("block_idle")
        self.sprite_fall = sprite("block_fall")
        self.sprite_rest = sprite("block_rest")
        self.reset()

    # ---- state helpers ----
    def reset(self):
        """Fresh fight (also used when the player respawns)."""
        self.state = self.HIDDEN
        self.hits = self.MAX_HITS
        self.timer = 0
        self.x = float(self.anchor_x)
        self.y = float(self.floor_top - self.size)
        self.vy = 0.0
        self.target_x = float(self.anchor_x)
        self.waves: list[ShockWave] = []
        self.fade = 255

    @property
    def activated(self) -> bool:
        return self.state != self.HIDDEN

    @property
    def defeated(self) -> bool:
        return self.state == self.DEFEATED

    @property
    def center_x(self) -> float:
        return self.x + self.size / 2

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.size, self.size)

    def wave_threat(self, px: float) -> bool:
        """True when a live wave is close enough to force a jump at ``px``."""
        return any(w.alive and abs(w.x - px) < 70 for w in self.waves)

    def _start_warning(self, player):
        self.state = self.WARNING
        self.timer = self.WARNING_TIME
        self.target_x = max(self.arena_left + TILE_SIZE,
                            min(player.center_x,
                                self.arena_right - TILE_SIZE * 2))

    # ---- frame update ----
    def update(self, player, particles, sound_fn, camera=None):
        if self.state == self.HIDDEN:
            # Wake only once the player has landed inside the arena, so the
            # first landing marker is always dodgeable.
            if player.center_x > self.trigger_x and player.on_ground:
                self._start_warning(player)
                sound_fn("sfx_magic")
            return
        if self.state == self.DEFEATED:
            self.fade = max(0, self.fade - 4)
            return

        if self.state == self.WARNING:
            self.timer -= 1
            if self.timer <= 0:
                self.state = self.FALLING
                self.x = float(self.target_x)
                self.y = float(-self.size)
                self.vy = 2.0
        elif self.state == self.FALLING:
            self.vy = min(14.0, self.vy + GRAVITY)
            self.y += self.vy
            if self.y >= self.floor_top - self.size:
                self.y = float(self.floor_top - self.size)
                self.state = self.CHARGE
                self.timer = self.CHARGE_TIME
                sound_fn("sfx_bump")
                if camera:
                    camera.shake(8, 18)
                particles.emit_burst(self.center_x, self.floor_top,
                                     (200, 200, 210), count=16, speed=5,
                                     size=5, life=25)
        elif self.state == self.CHARGE:
            self.timer -= 1
            if self.timer <= 0:
                self.state = self.SHOCKWAVE
                self.waves = [
                    ShockWave(self.center_x, self.floor_top, -1, 5 * TILE_SIZE),
                    ShockWave(self.center_x, self.floor_top, 1, 5 * TILE_SIZE),
                ]
                sound_fn("sfx_throw")
        elif self.state == self.SHOCKWAVE:
            for wave in self.waves:
                wave.update()
            self.waves = [w for w in self.waves if w.alive]
            if not self.waves:
                self.state = self.VULNERABLE
                self.timer = self.VULNERABLE_TIME
        elif self.state == self.VULNERABLE:
            self.timer -= 1
            if self.timer <= 0:
                self._start_warning(player)
                sound_fn("sfx_magic")
        elif self.state == self.SQUASHED:
            self.timer -= 1
            if self.timer <= 0:
                if self.hits <= 0:
                    self.state = self.DEFEATED
                    sound_fn("sfx_disappear")
                    particles.emit_burst(self.center_x, self.y, GOLD,
                                         count=30, speed=6, size=6, life=40)
                else:
                    self._start_warning(player)
                    sound_fn("sfx_magic")

        # ---- Player contact ----
        # Only telegraphed attacks hurt: the falling body and the waves.
        # While VULNERABLE the guardian is harmless and stompable.
        if self.state in (self.FALLING, self.CHARGE, self.SHOCKWAVE,
                          self.VULNERABLE):
            if player.rect.colliderect(self.rect):
                stomp = (player.vy > 0 and
                         player.prev_feet_y <= self.rect.top + 12)
                if stomp and self.state == self.VULNERABLE:
                    self.hits -= 1
                    self.state = self.SQUASHED
                    self.timer = self.SQUASHED_TIME
                    player.vy = JUMP_VELOCITY * 0.7
                    player.jumping = True
                    player.on_ground = False
                    sound_fn("sfx_bump")
                    particles.emit_burst(self.center_x, self.y, YELLOW,
                                         count=18, speed=5, size=5, life=30)
                    if camera:
                        camera.shake(5, 10)
                elif self.state != self.VULNERABLE and player.take_damage():
                    dx = player.center_x - self.center_x
                    player.vx = 6 if dx > 0 else -6
                    sound_fn("sfx_hurt")
                    if camera:
                        camera.shake(8, 15)

        # Waves burn on touch (jump over them)
        for wave in self.waves:
            if wave.alive and player.rect.colliderect(wave.rect):
                if player.take_damage():
                    sound_fn("sfx_hurt")
                    if camera:
                        camera.shake(6, 12)

    # ---- drawing ----
    def draw(self, surf, cam, frame: int):
        if self.state == self.HIDDEN:
            return
        ox, oy = cam.offset

        if self.state == self.WARNING:
            # Growing landing marker plus a faint drop column.
            cx = self.target_x + TILE_SIZE / 2
            t = 1.0 - self.timer / self.WARNING_TIME
            w = 20 + 44 * t
            column = pygame.Surface((6, self.floor_top), pygame.SRCALPHA)
            column.fill((220, 60, 60, 40 + int(50 * t)))
            surf.blit(column, (int(cx - 3 - ox), -oy))
            marker = pygame.Surface((int(w), 12), pygame.SRCALPHA)
            pygame.draw.ellipse(marker, (220, 60, 60, 120 + int(80 * t)),
                                marker.get_rect())
            surf.blit(marker, (int(cx - w / 2 - ox), int(self.floor_top - 8 - oy)))
        elif self.state == self.DEFEATED:
            flat = pygame.transform.smoothscale(
                self.sprite_rest, (self.size, max(6, self.size // 4)))
            flat.set_alpha(self.fade)
            surf.blit(flat, (int(self.x - ox),
                             int(self.floor_top - flat.get_height() - oy)))
        else:
            sprite = self.sprite_fall if self.state == self.FALLING \
                else self.sprite_rest if self.state in (self.VULNERABLE,
                                                        self.SQUASHED) \
                else self.sprite_idle
            if self.state == self.SQUASHED:
                sprite = pygame.transform.smoothscale(
                    sprite, (self.size, max(6, self.size // 2)))
                surf.blit(sprite, (int(self.x - ox),
                                   int(self.floor_top - sprite.get_height() - oy)))
            else:
                if self.state == self.CHARGE and frame % 6 < 3:
                    sprite = sprite.copy()
                    sprite.fill((255, 255, 255, 90),
                                special_flags=pygame.BLEND_RGBA_ADD)
                surf.blit(sprite, (int(self.x - ox), int(self.y - oy)))
            # Remaining-hit pips above the guardian
            if self.state in (self.CHARGE, self.SHOCKWAVE, self.VULNERABLE):
                for i in range(self.MAX_HITS):
                    color = RED if i < self.hits else (70, 70, 80)
                    pygame.draw.rect(
                        surf, color,
                        (int(self.center_x - 24 + i * 18 - ox),
                         int(self.y - 16 - oy), 12, 8))

        for wave in self.waves:
            wave.draw(surf, cam, frame)
