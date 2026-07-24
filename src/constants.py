"""
constants.py - Game configuration and constants for the platformer.
"""

import os

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE_DIR = os.path.join(BASE_DIR, "package")
SPRITE_DIR = os.path.join(PACKAGE_DIR, "Sprites")
SOUND_DIR = os.path.join(PACKAGE_DIR, "Sounds")

# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------
TILE_SIZE = 64
SCREEN_WIDTH = 1024          # 16 tiles visible
SCREEN_HEIGHT = 640          # 10 tiles visible
FPS = 60
TITLE = "Zeno's Adventure"

# ---------------------------------------------------------------------------
# Physics  (units: pixels / frame at 60 FPS)
# Tuned for responsive, satisfying platforming feel.
# ---------------------------------------------------------------------------
GRAVITY = 0.65               # slightly lower = floatier, more controllable jumps
MAX_FALL_SPEED = 16.0
JUMP_VELOCITY = -15.5        # gives ~3.3-tile jump height
JUMP_CUT_VELOCITY = -5.0     # tap jump = short hop, hold = full jump
PLAYER_FRICTION = 0.80       # snappy stop
PLAYER_MAX_SPEED = 6.5       # slightly faster feels better
CLIMB_SPEED = 3.5
COYOTE_TIME = 10             # ~0.17s grace after leaving platform
JUMP_BUFFER = 10             # ~0.17s buffered jump input
SPRING_VELOCITY = -24.0
INVINCIBILITY_FRAMES = 90    # ~1.5 s of i-frames after taking damage

# ---------------------------------------------------------------------------
# Player
# ---------------------------------------------------------------------------
PLAYER_SCALE = 0.55          # 128 px sprite -> ~70 px
ENEMY_SCALE = 0.9            # 64 px sprite -> ~58 px (for enemies)
COLLECTIBLE_SCALE = 0.75     # 64 px sprite -> ~48 px
STARTING_LIVES = 3
STARTING_HEALTH = 3
MAX_HEALTH = 5               # Skilled characters can reach 5 HP with hearts
MAX_HEALTH_NORMAL = 3        # Normal character (beige) is capped at 3 HP

CHARACTERS = ["beige", "green", "pink", "purple"]

# ---------------------------------------------------------------------------
# Difficulty
# ---------------------------------------------------------------------------
DIFFICULTY_ORDER = ("easy", "normal", "hard")
DIFFICULTY_CONFIG = {
    "easy": {
        "label": "Easy",
        "initial_lives": 5,
        "enemy_speed_mult": 0.85,
        "platform_speed_mult": 0.90,
        "conveyor_speed_mult": 0.85,
        "countdown": False,
        "checkpoint_mode": "all",
    },
    "normal": {
        "label": "Normal",
        "initial_lives": STARTING_LIVES,
        "enemy_speed_mult": 1.00,
        "platform_speed_mult": 1.00,
        "conveyor_speed_mult": 1.00,
        "countdown": False,
        "checkpoint_mode": "all",
    },
    "hard": {
        "label": "Hard",
        "initial_lives": 2,
        "enemy_speed_mult": 1.15,
        "platform_speed_mult": 1.15,
        "conveyor_speed_mult": 1.25,
        "countdown": True,
        "checkpoint_mode": "major",
    },
}

# ---------------------------------------------------------------------------
# Character abilities
# ---------------------------------------------------------------------------
SKILL_NONE = "none"
SKILL_DASH = "dash"
SKILL_DOUBLE_JUMP = "double_jump"
SKILL_SLOW_MO = "slow_mo"

# Map character color -> (skill_type, display_name, description, skill_key)
CHARACTER_SKILLS = {
    "beige": {
        "skill": SKILL_NONE,
        "name": "No Skill",
        "desc": "Classic: 3 HP, no skill",
        "key": "",
        "cooldown": 0,
        "duration": 0,
        "dash_speed": 0,
        "passive_speed_mult": 1.0,
        "passive_iframes_mult": 1.0,
        "max_health": MAX_HEALTH_NORMAL,
    },
    "green": {
        "skill": SKILL_DASH,
        "name": "Dash Strike",
        "desc": "X: Dash through enemies",
        "key": "X",
        "cooldown": 720,       # 12 seconds at 60 FPS
        "duration": 15,        # 0.25 seconds active
        "dash_speed": 18.0,
        "passive_speed_mult": 1.10,
        "passive_iframes_mult": 1.0,
        "max_health": MAX_HEALTH,
    },
    "pink": {
        "skill": SKILL_DOUBLE_JUMP,
        "name": "Double Jump",
        "desc": "Jump again in mid-air",
        "key": "Space",
        "cooldown": 0,          # no cooldown — resets on landing
        "duration": 0,
        "dash_speed": 0,
        "passive_speed_mult": 1.0,
        "passive_iframes_mult": 1.0,
        "jump_vel_mult": 1.15,  # 15% higher jump
        "max_health": MAX_HEALTH,
    },
    "purple": {
        "skill": SKILL_SLOW_MO,
        "name": "Time Slow",
        "desc": "C: Slow enemies for 3s",
        "key": "C",
        "cooldown": 900,       # 15 seconds
        "duration": 180,       # 3 seconds
        "dash_speed": 0,
        "passive_speed_mult": 1.0,
        "passive_iframes_mult": 1.5,  # 50% longer i-frames
        "max_health": MAX_HEALTH,
    },
}

# Star (invincibility) power-up
STAR_INVINCIBILITY_FRAMES = 300  # 5 seconds

# Charge crystal — resets skill cooldown
CHARGE_CRYSTAL_CHAR = 'c'

# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GRAY = (128, 128, 128)
DARK_GRAY = (40, 40, 50)
LIGHT_GRAY = (200, 200, 200)
RED = (220, 60, 60)
GREEN = (60, 200, 80)
BLUE = (70, 140, 240)
YELLOW = (240, 210, 60)
GOLD = (255, 200, 40)
PURPLE = (160, 80, 220)
PINK = (240, 130, 180)
ORANGE = (240, 150, 50)
TRANSPARENT = (0, 0, 0, 0)

# Theme palettes per level (background, text accent)
LEVEL_THEMES = {
    "grass": {
        "terrain": "grass",
        "bg_image": "background_color_trees",
        "bg_far": "background_color_hills",
        "solid_color": (92, 160, 72),
        "sky_top": (120, 200, 240),
        "sky_bot": (180, 230, 250),
    },
    "desert": {
        "terrain": "sand",
        "bg_image": "background_color_desert",
        "bg_far": "background_fade_desert",
        "solid_color": (210, 180, 120),
        "sky_top": (240, 180, 100),
        "sky_bot": (250, 220, 160),
    },
    "cave": {
        "terrain": "stone",
        "bg_image": "background_color_mushrooms",
        "bg_far": "background_fade_mushrooms",
        "solid_color": (90, 80, 100),
        "sky_top": (30, 25, 45),
        "sky_bot": (60, 45, 80),
    },
    "lava": {
        "terrain": "dirt",
        "bg_image": "background_fade_desert",
        "bg_far": "background_color_desert",
        "solid_color": (120, 60, 40),
        "sky_top": (80, 30, 20),
        "sky_bot": (160, 60, 30),
    },
    "sky": {
        "terrain": "purple",
        "bg_image": "background_clouds",
        "bg_far": "background_fade_hills",
        "solid_color": (130, 90, 180),
        "sky_top": (80, 120, 220),
        "sky_bot": (160, 200, 255),
    },
}

# ---------------------------------------------------------------------------
# Tile legend  (characters used in ASCII level maps)
# ---------------------------------------------------------------------------
#  '#'  solid grass-top block            '='  solid dirt block
#  'X'  solid stone block               'B'  solid brick block
#  'Q'  solid sand block                '-'  one-way plank platform
#  '~'  bridge (one-way)                'o'  bronze coin (1 pt)
#  'O'  silver coin (5 pt)              '0'  gold coin (10 pt)
#  'b'  blue gem (20 pt)               'g'  green gem
#  'u'  underwater blue gem             'c'  skill charge crystal
#  'r'  red gem                         'y'  yellow gem
#  'H'  heart (restore 1 HP)            '*'  star (50 pt)
#  '^'  spikes (damage)                 'L'  lava (damage)
#  'W'  water (slow, drown)             'j'  spring (bounce)
#  'K'  key (yellow)                    'k'  lock (yellow)
#  'D'  door (level exit)               'F'  flag (checkpoint)
#  'I'  ladder                          'C'  crate (pushable)
#  'M'  moving platform (horizontal)     '>'/'<' conveyor belts
#  'e'  enemy slime                      'a'  fire slime
#  's'  spike slime (dash/star only)     'h'  jumping frog
#  'q'  enemy bee (wide patrol)         'z'  enemy saw (static)
#  'Z'  enemy saw on a short track      'f'  enemy fish (horizontal)
#  'w'  enemy fish (vertical patrol)    'v'  enemy fly (tall patrol)
#  'G'  block guardian (mini-boss)      'V'  moving platform (vertical)
#  'n'  enemy snail                     '@'  bush (deco)
#  't'  tree (deco)                     '+'  cactus (deco)
#  'm'  mushroom (deco)                 'T'  torch (deco, animated)
#  'P'  player start
# ---------------------------------------------------------------------------

SOLID_TILES = frozenset("#=XBQj")     # 'j' spring is solid + bouncy
ONEWAY_TILES = frozenset("-~M")       # 'M' moving platform is one-way
HAZARD_TILES = frozenset("^L")
WATER_TILES = frozenset("W")
LADDER_TILES = frozenset("I")
SPRING_TILES = frozenset("j")
