from __future__ import annotations

"""
assets.py - Centralised asset loading with caching.
All sprites are converted with per-pixel alpha for fast blitting.
"""

import math
import os
import struct
import pygame

from .constants import SPRITE_DIR, SOUND_DIR, TILE_SIZE

# ---------------------------------------------------------------------------
# Internal caches
# ---------------------------------------------------------------------------
_image_cache: dict[str, pygame.Surface] = {}
_sound_cache: dict[str, pygame.mixer.Sound] = {}
_font_cache: dict[tuple[str, int], pygame.font.Font] = {}
_music_cache: dict[str, pygame.mixer.Sound] = {}
_music_channel: pygame.mixer.Channel | None = None
_music_name: str | None = None

# Sub-directory shortcuts
_TILES = os.path.join(SPRITE_DIR, "Tiles", "Default")
_CHARS = os.path.join(SPRITE_DIR, "Characters", "Default")
_ENEMIES = os.path.join(SPRITE_DIR, "Enemies", "Default")
_BGS = os.path.join(SPRITE_DIR, "Backgrounds", "Default")

_has_mixer = False


def init_audio():
    """Initialise the mixer (call once after pygame.init)."""
    global _has_mixer
    try:
        pygame.mixer.pre_init(44100, -16, 2, 512)
        pygame.mixer.init()
        _has_mixer = True
    except pygame.error:
        _has_mixer = False


# ---------------------------------------------------------------------------
# Image loading
# ---------------------------------------------------------------------------
def _load_raw(path: str) -> pygame.Surface:
    """Load an image file and convert to per-pixel alpha."""
    surf = pygame.image.load(path)
    return surf.convert_alpha()


def get_tile(name: str) -> pygame.Surface:
    """Load a tile sprite by filename (without extension)."""
    key = f"tile:{name}"
    if key not in _image_cache:
        path = os.path.join(_TILES, f"{name}.png")
        _image_cache[key] = _load_raw(path)
    return _image_cache[key]


def get_char(name: str) -> pygame.Surface:
    """Load a character sprite by filename (without extension)."""
    key = f"char:{name}"
    if key not in _image_cache:
        path = os.path.join(_CHARS, f"{name}.png")
        _image_cache[key] = _load_raw(path)
    return _image_cache[key]


def get_enemy(name: str) -> pygame.Surface:
    """Load an enemy sprite by filename (without extension)."""
    key = f"enemy:{name}"
    if key not in _image_cache:
        path = os.path.join(_ENEMIES, f"{name}.png")
        _image_cache[key] = _load_raw(path)
    return _image_cache[key]


def get_background(name: str) -> pygame.Surface:
    """Load a background sprite by filename (without extension)."""
    key = f"bg:{name}"
    if key not in _image_cache:
        path = os.path.join(_BGS, f"{name}.png")
        _image_cache[key] = _load_raw(path)
    return _image_cache[key]


# ---------------------------------------------------------------------------
# Scaled sprites (cached)
# ---------------------------------------------------------------------------
def _scale(surf: pygame.Surface, factor: float) -> pygame.Surface:
    if factor == 1.0:
        return surf
    w = max(1, int(surf.get_width() * factor))
    h = max(1, int(surf.get_height() * factor))
    return pygame.transform.smoothscale(surf, (w, h))


def get_tile_scaled(name: str, size: int = TILE_SIZE) -> pygame.Surface:
    key = f"tile_s:{name}:{size}"
    if key not in _image_cache:
        surf = get_tile(name)
        _image_cache[key] = pygame.transform.smoothscale(surf, (size, size))
    return _image_cache[key]


# ---------------------------------------------------------------------------
# Character sprite sets
# ---------------------------------------------------------------------------
def load_character_set(color: str, scale: float = 0.55) -> dict[str, list[pygame.Surface]]:
    """
    Return a dict of animation frames for the given character colour.

    Keys: idle, walk (2 frames), jump, duck, hit, climb (2 frames), front
    Each value is a list of scaled Surfaces.
    """
    key = f"charset:{color}:{scale}"
    if key in _image_cache:
        return _image_cache[key]

    def s(name):
        return _scale(get_char(f"character_{color}_{name}"), scale)

    frames = {
        "idle": [s("idle")],
        "walk": [s("walk_a"), s("walk_b")],
        "jump": [s("jump")],
        "duck": [s("duck")],
        "hit": [s("hit")],
        "climb": [s("climb_a"), s("climb_b")],
        "front": [s("front")],
    }
    _image_cache[key] = frames
    return frames


# ---------------------------------------------------------------------------
# Enemy sprite sets
# ---------------------------------------------------------------------------
def load_enemy_set(scale: float = 0.9) -> dict[str, dict]:
    """Return a dict of enemy-type -> {state: [frames]}."""
    key = f"enemyset:{scale}"
    if key in _image_cache:
        return _image_cache[key]

    def s(name):
        return _scale(get_enemy(name), scale)

    sets = {
        "slime": {
            "walk": [s("slime_normal_walk_a"), s("slime_normal_walk_b")],
            "rest": [s("slime_normal_rest")],
            "flat": [s("slime_normal_flat")],
        },
        "slime_fire": {
            "walk": [s("slime_fire_walk_a"), s("slime_fire_walk_b")],
            "rest": [s("slime_fire_rest")],
        },
        "slime_spike": {
            "walk": [s("slime_spike_walk_a"), s("slime_spike_walk_b")],
            "rest": [s("slime_spike_rest")],
        },
        "bee": {
            "fly": [s("bee_a"), s("bee_b")],
            "rest": [s("bee_rest")],
        },
        "saw": {
            "spin": [s("saw_a"), s("saw_b")],
            "rest": [s("saw_rest")],
        },
        "fish_blue": {
            "swim": [s("fish_blue_swim_a"), s("fish_blue_swim_b")],
            "rest": [s("fish_blue_rest")],
        },
        "fish_yellow": {
            "swim": [s("fish_yellow_swim_a"), s("fish_yellow_swim_b")],
            "rest": [s("fish_yellow_rest")],
        },
        "fish_purple": {
            "swim": [s("fish_purple_up"), s("fish_purple_down")],
            "rest": [s("fish_purple_rest")],
        },
        "fly": {
            "fly": [s("fly_a"), s("fly_b")],
            "rest": [s("fly_rest")],
        },
        "snail": {
            "walk": [s("snail_walk_a"), s("snail_walk_b")],
            "rest": [s("snail_rest")],
            "shell": [s("snail_shell")],
        },
        "frog": {
            "idle": [s("frog_idle")],
            "jump": [s("frog_jump")],
            "rest": [s("frog_rest")],
        },
        "ladybug": {
            "walk": [s("ladybug_walk_a"), s("ladybug_walk_b")],
            "fly": [s("ladybug_fly")],
            "rest": [s("ladybug_rest")],
        },
        "mouse": {
            "walk": [s("mouse_walk_a"), s("mouse_walk_b")],
            "rest": [s("mouse_rest")],
        },
        "worm": {
            "move": [s("worm_normal_move_a"), s("worm_normal_move_b")],
            "rest": [s("worm_normal_rest")],
        },
    }
    _image_cache[key] = sets
    return sets


# ---------------------------------------------------------------------------
# Sound
# ---------------------------------------------------------------------------
def get_sound(name: str) -> pygame.mixer.Sound | None:
    """Load an .ogg sound file.  Returns None if mixer unavailable."""
    if not _has_mixer:
        return None
    key = f"snd:{name}"
    if key not in _sound_cache:
        path = os.path.join(SOUND_DIR, f"{name}.ogg")
        if os.path.exists(path):
            _sound_cache[key] = pygame.mixer.Sound(path)
        else:
            return None
    return _sound_cache[key]


def _generated_victory_music() -> pygame.mixer.Sound | None:
    """Small loopable chiptune used when no packaged music file exists."""
    if not _has_mixer:
        return None
    key = "music:victory:generated"
    if key in _music_cache:
        return _music_cache[key]

    init = pygame.mixer.get_init()
    sample_rate = init[0] if init else 44100
    notes = [
        (523.25, 0.20), (659.25, 0.20), (783.99, 0.20), (1046.50, 0.38),
        (987.77, 0.18), (783.99, 0.20), (880.00, 0.24), (1046.50, 0.42),
        (659.25, 0.20), (783.99, 0.20), (987.77, 0.20), (1318.51, 0.48),
        (1174.66, 0.22), (987.77, 0.22), (1046.50, 0.55),
    ]
    payload = bytearray()
    volume = 0.18
    for freq, seconds in notes:
        frames = int(sample_rate * seconds)
        fade_frames = max(1, int(sample_rate * 0.015))
        for i in range(frames):
            env = 1.0
            if i < fade_frames:
                env = i / fade_frames
            elif frames - i < fade_frames:
                env = (frames - i) / fade_frames
            sample = int(math.sin(math.tau * freq * i / sample_rate) * 32767 * volume * env)
            payload.extend(struct.pack("<hh", sample, sample))
    sound = pygame.mixer.Sound(buffer=bytes(payload))
    _music_cache[key] = sound
    return sound


def play_music(name: str, muted: bool = False):
    """Loop a named music cue. Missing files degrade to a safe no-op/fallback."""
    global _music_channel, _music_name
    if muted or not _has_mixer:
        stop_music()
        return
    if _music_name == name:
        return

    stop_music()
    path = os.path.join(SOUND_DIR, f"music_{name}.ogg")
    if os.path.exists(path):
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.play(-1)
            _music_name = name
            return
        except pygame.error:
            pass

    sound = _generated_victory_music() if name == "victory" else None
    if sound is None:
        return
    _music_channel = pygame.mixer.find_channel(force=True)
    if _music_channel:
        _music_channel.play(sound, loops=-1)
        _music_name = name


def stop_music():
    global _music_channel, _music_name
    try:
        pygame.mixer.music.stop()
    except pygame.error:
        pass
    if _music_channel:
        _music_channel.stop()
    _music_channel = None
    _music_name = None


# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------
def get_font(size: int, bold: bool = False) -> pygame.font.Font:
    key = (size, bold)
    if key not in _font_cache:
        font = pygame.font.SysFont("Arial,DejaVu Sans,Helvetica", size, bold=bold)
        _font_cache[key] = font
    return _font_cache[key]


# ---------------------------------------------------------------------------
# Terrain tile helper
# ---------------------------------------------------------------------------
def terrain_block_name(theme: str) -> str:
    """Return the base terrain block tile name for a given theme."""
    mapping = {
        "grass": "terrain_grass_block",
        "dirt": "terrain_dirt_block",
        "stone": "bricks_grey",
        "sand": "terrain_sand_block",
        "purple": "terrain_purple_block",
        "snow": "terrain_snow_block",
    }
    return mapping.get(theme, "terrain_grass_block")


def terrain_top_name(theme: str) -> str:
    """Return the terrain top tile name for a given theme."""
    mapping = {
        "grass": "terrain_grass_block_top",
        "dirt": "terrain_dirt_block_top",
        "stone": "brick_grey",
        "sand": "terrain_sand_block_top",
        "purple": "terrain_purple_block_top",
        "snow": "terrain_snow_block_top",
    }
    return mapping.get(theme, "terrain_grass_block_top")
