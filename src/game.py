from __future__ import annotations

"""
game.py - TileMap, game state machine, rendering, and main loop.

States: MENU → CHARACTER_SELECT → PLAYING → (PAUSED) → LEVEL_COMPLETE
        → next level ... → VICTORY   (or GAME_OVER at any point)
"""

import os
import math
import random

import pygame

from . import assets
from .constants import (
    TILE_SIZE, SCREEN_WIDTH, SCREEN_HEIGHT, FPS, TITLE,
    JUMP_VELOCITY,
    LEVEL_THEMES, CHARACTERS, STARTING_LIVES, STARTING_HEALTH,
    DIFFICULTY_ORDER, DIFFICULTY_CONFIG,
    MAX_HEALTH,
    WHITE, BLACK, GRAY, LIGHT_GRAY, RED, GREEN, BLUE, YELLOW,
    GOLD, PURPLE, PINK, ORANGE, DARK_GRAY,
)
from .entities import (
    Camera, ParticleSystem, Collectible, Enemy, Player, MovingPlatform, FirePatch,
    BlockGuardian,
)
from .levels import LEVELS
from .progression import ProgressionStore


# Character-specific skill tutorial shown before Green Hills' first crystal.
SKILL_HINTS = {
    "beige": "Classic Challenge: pure platforming, no skill!",
    "green": "Skill: press X to Dash through enemies!",
    "pink": "Skill: press Jump again in mid-air!",
    "purple": "Skill: press C to slow down time!",
}

# One-time rule summary the first time a star power-up is collected.
STAR_RULE_HINT = "Star Power! Smash enemies — it also blocks one hazard, then ends."


# ---------------------------------------------------------------------------
# TileMap
# ---------------------------------------------------------------------------
class TileMap:
    """Parses ASCII level data and provides collision / rendering helpers."""

    def __init__(self, level_data: dict):
        self.name = level_data["name"]
        self.theme = level_data["theme"]
        self.raw_map = level_data["map"]
        self.height = len(self.raw_map)
        self.width = max(len(row) for row in self.raw_map)
        self.pixel_w = self.width * TILE_SIZE
        self.pixel_h = self.height * TILE_SIZE

        # Tile sets
        self.solids: set[tuple[int, int]] = set()
        self.oneways: set[tuple[int, int]] = set()
        self.springs: set[tuple[int, int]] = set()
        self.hazards: set[tuple[int, int]] = set()
        self.water: set[tuple[int, int]] = set()
        self.ladders: set[tuple[int, int]] = set()
        self.conveyors: dict[tuple[int, int], int] = {}
        self.locks: set[tuple[int, int]] = set()
        self.decorations: list[tuple[int, int, str]] = []
        self.torches: list[tuple[int, int]] = []

        # Entities
        self.collectibles: list[Collectible] = []
        self.enemies: list[Enemy] = []
        self.moving_platforms: list[MovingPlatform] = []
        self.boss: BlockGuardian | None = None
        self._boss_anchor: tuple[int, int] | None = None

        # Special positions
        self.player_start = (0, 0)
        self.door_pos = None
        self.key_positions: list[tuple[int, int]] = []
        self.flag_positions: list[tuple[int, int]] = []
        self.checkpoint = None

        # State
        self.locks_open = False
        self.has_key = False
        self.door_open = False
        self.spring_timers: dict[tuple[int, int], int] = {}

        self._parse()
        self._prerender()

    def _parse(self):
        for row_idx, row in enumerate(self.raw_map):
            padded = row.ljust(self.width)
            for col_idx, ch in enumerate(padded):
                if ch == " ":
                    continue
                pos = (col_idx, row_idx)
                if ch in "#=XBQ":
                    self.solids.add(pos)
                elif ch in "-~":
                    self.oneways.add(pos)
                elif ch == "j":
                    self.springs.add(pos)
                    self.solids.add(pos)  # springs are solid
                elif ch in "^L":
                    self.hazards.add(pos)
                elif ch == "W":
                    self.water.add(pos)
                elif ch == "I":
                    self.ladders.add(pos)
                elif ch == "k":
                    self.locks.add(pos)
                elif ch in "oO0bgryH*c":
                    self.collectibles.append(Collectible(col_idx, row_idx, ch))
                elif ch == "u":
                    self.water.add(pos)
                    self.collectibles.append(Collectible(col_idx, row_idx, "b"))
                elif ch in "eqzfvnashwZ":
                    self.enemies.append(Enemy(col_idx, row_idx, ch))
                    if ch in "fw":
                        self.water.add(pos)
                elif ch == "G":
                    self._boss_anchor = (col_idx, row_idx)
                elif ch in "><":
                    self.conveyors[pos] = 1 if ch == ">" else -1
                    self.solids.add(pos)
                elif ch == "M":
                    self.moving_platforms.append(
                        MovingPlatform(col_idx, row_idx, travel=5, speed=1.5)
                    )
                elif ch == "V":
                    # Vertical shuttle; gentle speed so its first appearance
                    # stays readable ( rises from the anchor row ).
                    self.moving_platforms.append(
                        MovingPlatform(col_idx, row_idx, travel=3, speed=0.8,
                                       axis="y")
                    )
                elif ch == "P":
                    self.player_start = (col_idx * TILE_SIZE, row_idx * TILE_SIZE)
                    self.checkpoint = self.player_start
                elif ch == "D":
                    self.door_pos = (col_idx, row_idx)
                elif ch == "K":
                    self.key_positions.append((col_idx, row_idx))
                elif ch == "F":
                    self.flag_positions.append((col_idx, row_idx))
                elif ch == "T":
                    self.torches.append(pos)
                elif ch in "@t+m":
                    self.decorations.append((col_idx, row_idx, ch))

        # If no door, use last solid position as exit (fallback)
        if self.door_pos is None:
            self.door_pos = (self.width - 2, self.height - 3)

        # ------------------------------------------------------------------
        # Snap ground-based items to the nearest ground below.
        # This fixes decorations, flags, keys, locks, doors, and walker
        # enemies that were placed one or more rows too high in the ASCII
        # map, causing them to appear floating in mid-air.
        # ------------------------------------------------------------------
        self.decorations = [
            (col, self._snap_row_to_ground(col, row), ch)
            for (col, row, ch) in self.decorations
        ]
        self.flag_positions = [
            (col, self._snap_row_to_ground(col, row))
            for (col, row) in self.flag_positions
        ]
        self.key_positions = [
            (col, self._snap_row_to_ground(col, row))
            for (col, row) in self.key_positions
        ]
        self.locks = {
            (col, self._snap_row_to_ground(col, row))
            for (col, row) in self.locks
        }
        if self.door_pos:
            dcol, drow = self.door_pos
            self.door_pos = (dcol, self._snap_row_to_ground(dcol, drow))

        # Snap walker enemies (slime, snail) to ground so they start on it
        for enemy in self.enemies:
            if enemy.etype in ("slime", "snail", "fire_slime", "spike_slime", "frog"):
                new_row = self._snap_row_to_ground(enemy.col, enemy.row)
                enemy.row = new_row
                # Place enemy so feet rest on top of the ground tile
                # (new_row is the walking level; ground is at new_row + 1)
                ground_top = (new_row + 1) * TILE_SIZE
                enemy.y = ground_top - enemy.size
                enemy.start_y = enemy.y
                enemy.fly_base_y = enemy.y
                pad = enemy.size * 0.15
                enemy.hitbox.y = enemy.y + pad

        # Build the block guardian (if any): the arena is the contiguous
        # floor segment beneath its anchor.
        if self._boss_anchor:
            acol, arow = self._boss_anchor
            floor_row = arow + 1
            left = acol
            while left > 0 and self.is_solid_at(left - 1, floor_row):
                left -= 1
            right = acol
            while right < self.width - 1 and self.is_solid_at(right + 1, floor_row):
                right += 1
            self.boss = BlockGuardian(
                acol, arow, left * TILE_SIZE, (right + 1) * TILE_SIZE
            )

    # ---- Solidity queries ----
    def is_solid_at(self, col: int, row: int) -> bool:
        if col < 0 or col >= self.width or row < 0 or row >= self.height:
            return col < 0 or col >= self.width  # side walls solid, top/bottom open
        if (col, row) in self.solids:
            return True
        if (col, row) in self.locks and not self.locks_open:
            return True
        return False

    def has_ground_below(self, col: int, start_row: int, max_depth: int = 5) -> bool:
        """Check if there's any solid or one-way platform within max_depth rows below."""
        for r in range(start_row, min(start_row + max_depth, self.height)):
            if self.is_solid_at(col, r):
                return True
            if (col, r) in self.oneways:
                return True
        return False

    def _snap_row_to_ground(self, col: int, row: int) -> int:
        """Return the walking-level row just above the nearest ground below (col, row).

        Searches downward from row+1 for the first solid or one-way platform.
        If found at ground_row, returns ground_row - 1 (the row whose bottom
        rests on the ground).  If no ground is found below, returns the
        original row unchanged.
        """
        for r in range(row + 1, self.height):
            if self.is_solid_at(col, r) or (col, r) in self.oneways:
                return r - 1
        return row

    def is_ladder_at(self, col: int, row: int) -> bool:
        if col < 0 or col >= self.width or row < 0 or row >= self.height:
            return False
        return (col, row) in self.ladders

    def rect_collides_solid(self, rect: pygame.Rect) -> bool:
        # Do NOT clamp col range to [0, width-1]: is_solid_at() declares
        # invisible side walls at col < 0 and col >= width.  Clamping
        # would skip those columns and let the player walk off the map.
        col0 = rect.left // TILE_SIZE
        col1 = rect.right // TILE_SIZE
        row0 = rect.top // TILE_SIZE
        row1 = rect.bottom // TILE_SIZE
        for r in range(int(row0), int(row1) + 1):
            for c in range(int(col0), int(col1) + 1):
                if self.is_solid_at(c, r):
                    return True
        return False

    def get_solid_tiles_in_rect(self, rect: pygame.Rect) -> list[pygame.Rect]:
        result = []
        col0 = rect.left // TILE_SIZE
        col1 = rect.right // TILE_SIZE
        row0 = rect.top // TILE_SIZE
        row1 = rect.bottom // TILE_SIZE
        for r in range(int(row0), int(row1) + 1):
            for c in range(int(col0), int(col1) + 1):
                if self.is_solid_at(c, r):
                    # For out-of-bounds columns the tile rect is virtual
                    # (placed at the boundary) so collision resolution
                    # pushes the player back inside the map.
                    result.append(pygame.Rect(c * TILE_SIZE, r * TILE_SIZE, TILE_SIZE, TILE_SIZE))
        return result

    def get_oneway_tiles_in_rect(self, rect: pygame.Rect) -> list[pygame.Rect]:
        result = []
        col0 = max(0, rect.left // TILE_SIZE)
        col1 = min(self.width - 1, rect.right // TILE_SIZE)
        row0 = max(0, rect.top // TILE_SIZE)
        row1 = min(self.height - 1, rect.bottom // TILE_SIZE)
        for r in range(int(row0), int(row1) + 1):
            for c in range(int(col0), int(col1) + 1):
                if (c, r) in self.oneways:
                    result.append(pygame.Rect(c * TILE_SIZE, r * TILE_SIZE, TILE_SIZE, TILE_SIZE))
        return result

    def get_spring_tiles_in_rect(self, rect: pygame.Rect) -> list[pygame.Rect]:
        result = []
        col0 = max(0, rect.left // TILE_SIZE)
        col1 = min(self.width - 1, rect.right // TILE_SIZE)
        row0 = max(0, rect.top // TILE_SIZE)
        row1 = min(self.height - 1, rect.bottom // TILE_SIZE)
        for r in range(int(row0), int(row1) + 1):
            for c in range(int(col0), int(col1) + 1):
                if (c, r) in self.springs:
                    result.append(pygame.Rect(c * TILE_SIZE, r * TILE_SIZE, TILE_SIZE, TILE_SIZE))
        return result

    def rect_collides_hazard(self, rect: pygame.Rect) -> bool:
        col0 = max(0, rect.left // TILE_SIZE)
        col1 = min(self.width - 1, rect.right // TILE_SIZE)
        row0 = max(0, rect.top // TILE_SIZE)
        row1 = min(self.height - 1, rect.bottom // TILE_SIZE)
        for r in range(int(row0), int(row1) + 1):
            for c in range(int(col0), int(col1) + 1):
                if (c, r) in self.hazards:
                    return True
        return False

    def rect_collides_water(self, rect: pygame.Rect) -> bool:
        col0 = max(0, rect.left // TILE_SIZE)
        col1 = min(self.width - 1, rect.right // TILE_SIZE)
        row0 = max(0, rect.top // TILE_SIZE)
        row1 = min(self.height - 1, rect.bottom // TILE_SIZE)
        for r in range(int(row0), int(row1) + 1):
            for c in range(int(col0), int(col1) + 1):
                if (c, r) in self.water:
                    return True
        return False

    def conveyor_at_feet(self, rect: pygame.Rect) -> int:
        """Return belt direction when the actor is standing on a conveyor."""
        row = int((rect.bottom + 2) // TILE_SIZE)
        for col in range(int(rect.left // TILE_SIZE), int(rect.right // TILE_SIZE) + 1):
            direction = self.conveyors.get((col, row))
            if direction:
                return direction
        return 0

    # ---- Rendering ----
    def _tile_sprite(self, col: int, row: int, ch: str) -> pygame.Surface | None:
        """Return the sprite for a given solid tile, considering theme + neighbours."""
        theme = LEVEL_THEMES.get(self.theme, LEVEL_THEMES["grass"])

        if ch == "#":
            # Themed terrain top
            above_empty = (col, row - 1) not in self.solids and (col, row - 1) not in self.locks
            name = assets.terrain_top_name(theme["terrain"]) if above_empty else assets.terrain_block_name(theme["terrain"])
            return assets.get_tile_scaled(name, TILE_SIZE)
        elif ch == "=":
            above_empty = (col, row - 1) not in self.solids and (col, row - 1) not in self.locks
            name = assets.terrain_top_name(theme["terrain"]) if above_empty else assets.terrain_block_name(theme["terrain"])
            return assets.get_tile_scaled(name, TILE_SIZE)
        elif ch == "X":
            return assets.get_tile_scaled("bricks_grey", TILE_SIZE)
        elif ch == "B":
            return assets.get_tile_scaled("bricks_brown", TILE_SIZE)
        elif ch == "Q":
            above_empty = (col, row - 1) not in self.solids and (col, row - 1) not in self.locks
            name = "terrain_sand_block_top" if above_empty else "terrain_sand_block"
            return assets.get_tile_scaled(name, TILE_SIZE)
        elif ch == "j":
            return assets.get_tile_scaled("spring", TILE_SIZE)
        elif ch in "><":
            sprite = assets.get_tile_scaled("conveyor", TILE_SIZE)
            return pygame.transform.flip(sprite, True, False) if ch == "<" else sprite
        return None

    def _prerender(self):
        """Pre-render all static tiles to a large surface for fast blitting."""
        self.bg_surface = pygame.Surface((self.pixel_w, self.pixel_h), pygame.SRCALPHA)

        # Build a char lookup for the map
        char_map: dict[tuple[int, int], str] = {}
        for row_idx, row in enumerate(self.raw_map):
            padded = row.ljust(self.width)
            for col_idx, ch in enumerate(padded):
                if ch != " ":
                    char_map[(col_idx, row_idx)] = ch

        # Draw solid tiles (skip springs — they're drawn in draw_animated)
        for (col, row) in self.solids:
            if (col, row) in self.springs:
                continue
            ch = char_map.get((col, row), "#")
            sprite = self._tile_sprite(col, row, ch)
            if sprite:
                self.bg_surface.blit(sprite, (col * TILE_SIZE, row * TILE_SIZE))

        # Draw one-way platforms
        plank = assets.get_tile_scaled("block_planks", TILE_SIZE)
        bridge = assets.get_tile_scaled("bridge_logs", TILE_SIZE)
        for (col, row) in self.oneways:
            ch = char_map.get((col, row), "-")
            sprite = bridge if ch == "~" else plank
            # Draw at bottom of tile cell for platform look
            self.bg_surface.blit(sprite, (col * TILE_SIZE, row * TILE_SIZE))

        # Draw ladders
        for (col, row) in self.ladders:
            above = (col, row - 1) in self.ladders
            below = (col, row + 1) in self.ladders
            if not above:
                sprite = assets.get_tile_scaled("ladder_top", TILE_SIZE)
            elif not below:
                sprite = assets.get_tile_scaled("ladder_bottom", TILE_SIZE)
            else:
                sprite = assets.get_tile_scaled("ladder_middle", TILE_SIZE)
            self.bg_surface.blit(sprite, (col * TILE_SIZE, row * TILE_SIZE))

        # Draw locks (if not open)
        if not self.locks_open:
            lock_sprite = assets.get_tile_scaled("lock_yellow", TILE_SIZE)
            for (col, row) in self.locks:
                self.bg_surface.blit(lock_sprite, (col * TILE_SIZE, row * TILE_SIZE))

        # Draw decorations
        deco_sprites = {
            "@": assets.get_tile_scaled("bush", TILE_SIZE),
            "+": assets.get_tile_scaled("cactus", TILE_SIZE),
            "m": assets.get_tile_scaled("mushroom_red", TILE_SIZE),
            "t": assets.get_tile_scaled("bush", TILE_SIZE),
        }
        for (col, row, ch) in self.decorations:
            sprite = deco_sprites.get(ch)
            if sprite:
                self.bg_surface.blit(sprite, (col * TILE_SIZE, row * TILE_SIZE))

        # Draw door
        if self.door_pos:
            door_sprite = assets.get_tile_scaled(
                "door_open" if self.door_open else "door_closed", TILE_SIZE
            )
            self.bg_surface.blit(door_sprite, (self.door_pos[0] * TILE_SIZE, self.door_pos[1] * TILE_SIZE))
            # Door top
            door_top = assets.get_tile_scaled(
                "door_open_top" if self.door_open else "door_closed_top", TILE_SIZE
            )
            self.bg_surface.blit(door_top, (self.door_pos[0] * TILE_SIZE, (self.door_pos[1] - 1) * TILE_SIZE))

        # Draw flags
        flag_sprite = assets.get_tile_scaled("flag_yellow_a", TILE_SIZE)
        for (col, row) in self.flag_positions:
            self.bg_surface.blit(flag_sprite, (col * TILE_SIZE, row * TILE_SIZE))

        # Draw keys (if not collected)
        if not self.has_key:
            key_sprite = assets.get_tile_scaled("key_yellow", TILE_SIZE)
            for (col, row) in self.key_positions:
                self.bg_surface.blit(key_sprite, (col * TILE_SIZE, row * TILE_SIZE))

    def draw_static(self, surf: pygame.Surface, cam: Camera):
        ox, oy = cam.offset
        # Only draw the visible portion
        src_x = max(0, int(ox))
        src_y = max(0, int(oy))
        src_w = min(SCREEN_WIDTH, self.pixel_w - src_x)
        src_h = min(SCREEN_HEIGHT, self.pixel_h - src_y)
        if src_w > 0 and src_h > 0:
            surf.blit(self.bg_surface, (src_x - ox, src_y - oy), (src_x, src_y, src_w, src_h))

    def draw_animated(self, surf: pygame.Surface, cam: Camera, frame: int):
        """Draw animated tiles: springs, hazards, water, torches."""
        ox, oy = cam.offset

        # Springs (show compressed when recently activated)
        spring_normal = assets.get_tile_scaled("spring", TILE_SIZE)
        spring_out = assets.get_tile_scaled("spring_out", TILE_SIZE)
        for (col, row) in self.springs:
            x = col * TILE_SIZE - ox
            y = row * TILE_SIZE - oy
            if self.spring_timers.get((col, row), 0) > 0:
                surf.blit(spring_out, (x, y))
            else:
                surf.blit(spring_normal, (x, y))

        # Spikes
        spike_sprite = assets.get_tile_scaled("spikes", TILE_SIZE)
        for (col, row) in self.hazards:
            ch = self._char_at(col, row)
            if ch == "^":
                surf.blit(spike_sprite, (col * TILE_SIZE - ox, row * TILE_SIZE - oy))

        # Lava (animated by shifting slightly)
        lava_top = assets.get_tile_scaled("lava_top", TILE_SIZE)
        lava = assets.get_tile_scaled("lava", TILE_SIZE)
        for (col, row) in self.hazards:
            ch = self._char_at(col, row)
            if ch == "L":
                above_lava = self._char_at(col, row - 1) != "L"
                x = col * TILE_SIZE - ox
                y = row * TILE_SIZE - oy
                if above_lava:
                    surf.blit(lava_top, (x, y))
                else:
                    surf.blit(lava, (x, y))

        # Water
        water_top = assets.get_tile_scaled("water_top", TILE_SIZE)
        water = assets.get_tile_scaled("water", TILE_SIZE)
        for (col, row) in self.water:
            above_water = self._char_at(col, row - 1) != "W"
            x = col * TILE_SIZE - ox
            y = row * TILE_SIZE - oy
            if above_water:
                surf.blit(water_top, (x, y))
            else:
                surf.blit(water, (x, y))

        # Torches (animated)
        torch_frames = [
            assets.get_tile_scaled("torch_on_a", TILE_SIZE),
            assets.get_tile_scaled("torch_on_b", TILE_SIZE),
        ]
        for (col, row) in self.torches:
            f = torch_frames[(frame // 10) % 2]
            surf.blit(f, (col * TILE_SIZE - ox, row * TILE_SIZE - oy))

        # Flags (waving)
        flag_frames = [
            assets.get_tile_scaled("flag_yellow_a", TILE_SIZE),
            assets.get_tile_scaled("flag_yellow_b", TILE_SIZE),
        ]
        for (col, row) in self.flag_positions:
            f = flag_frames[(frame // 15) % 2]
            surf.blit(f, (col * TILE_SIZE - ox, row * TILE_SIZE - oy))

    def _char_at(self, col: int, row: int) -> str:
        if 0 <= row < self.height and 0 <= col < self.width:
            padded = self.raw_map[row].ljust(self.width)
            if col < len(padded):
                return padded[col]
        return " "

    def open_locks(self):
        self.locks_open = True
        self._prerender()

    def collect_key(self):
        self.has_key = True
        self.open_locks()

    def open_door(self):
        self.door_open = True
        self._prerender()


# ---------------------------------------------------------------------------
# Game
# ---------------------------------------------------------------------------
class Game:
    # State constants
    S_MENU = "menu"
    S_CHARSELECT = "charselect"
    S_PLAYING = "playing"
    S_PAUSED = "paused"
    S_LEVEL_COMPLETE = "level_complete"
    S_GAME_OVER = "game_over"
    S_VICTORY = "victory"
    S_CONTROLS = "controls"
    S_LEVEL_SELECT = "level_select"

    def __init__(self, progress_path: str | None = None):
        pygame.init()
        assets.init_audio()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption(TITLE)
        self.clock = pygame.time.Clock()

        project_root = os.path.dirname(os.path.dirname(__file__))
        self.progress = ProgressionStore(
            progress_path or os.path.join(project_root, "save.json"), len(LEVELS)
        )
        self.muted = bool(self.progress.data["settings"].get("muted", False))
        self.difficulty = self._normalise_difficulty(
            self.progress.data["settings"].get("difficulty", "normal")
        )
        self.state = self.S_MENU
        self.state_timer = 0
        self.frame_count = 0
        self.game_over_reason = ""

        # Game data
        self.character_color = "beige"
        self.current_level = 0
        self.total_score = 0
        self.total_time = 0.0
        self.level_time = 0.0
        self.high_score = max(
            int(self.progress.data.get("high_score", 0)), self._load_high_score()
        )
        self.new_high_score = False
        self.progress.data["high_score"] = self.high_score

        # Level objects
        self.tilemap: TileMap | None = None
        self.player: Player | None = None
        self.camera: Camera | None = None
        self.particles = ParticleSystem()

        # Menu
        self.menu_index = 0
        self.char_index = 0
        self.menu_items = []
        self._sync_menu_items()
        self.level_select_index = 0

        # Transition
        self.transition_alpha = 0
        self.transition_dir = 0  # 0=none, 1=fading out, -1=fading in

        # Fonts
        self.font_big = assets.get_font(56, bold=True)
        self.font_med = assets.get_font(32, bold=True)
        self.font_small = assets.get_font(20)
        self.font_tiny = assets.get_font(16)

        # Cached surfaces
        self._sky_cache: dict[str, pygame.Surface] = {}
        self._menu_bg: pygame.Surface | None = None
        self._bg_scaled_cache: dict[str, pygame.Surface] = {}

        # Key/lock HUD
        self.show_key_msg = 0
        # "The Guardian seals the door" message timer
        self.door_sealed_msg = 0

        # Slow-mo skill timer
        self.slow_mo_timer = 0
        self.fire_patches: list[FirePatch] = []

        # Tutorial hints (Level 1). The "skill" entry is resolved against the
        # chosen character in start_level() (Beige shows Classic Challenge).
        self._tutorial_hint_specs = [
            (2, "Arrow Keys / WASD: Move    Space: Jump"),
            (11, "Hold Jump for higher jumps!"),
            (28, "skill"),  # just before the first charge crystal (col 32)
            (42, "Stomp enemies from above!"),
            (54, "Find the Key to open the Lock!"),
            (69, "Reach the Door to complete the level!"),
        ]
        self._tutorial_hints: list[dict] = []
        self.active_tutorial_hint = None
        self.tutorial_hint_timer = 0
        self.show_tutorial = bool(
            self.progress.data["settings"].get("tutorial_hints", True)
        )
        self._star_hint_shown = False
        self.achievement_toasts: list[dict] = []
        self.level_achievements_unlocked: list[dict] = []
        self._final_result: dict | None = None

    # ---- Utility ----
    def _normalise_difficulty(self, value) -> str:
        value = str(value).lower()
        return value if value in DIFFICULTY_CONFIG else "normal"

    def _difficulty_rules(self) -> dict:
        return DIFFICULTY_CONFIG.get(self.difficulty, DIFFICULTY_CONFIG["normal"])

    def _sync_menu_items(self):
        label = self._difficulty_rules().get("label", self.difficulty.title())
        self.menu_items = [
            "Start Game",
            "Select Character",
            "Controls",
            "Level Select",
            f"Difficulty: {label}",
            "Quit",
        ]
        self.menu_index = min(getattr(self, "menu_index", 0), len(self.menu_items) - 1)

    def _cycle_difficulty(self):
        idx = DIFFICULTY_ORDER.index(self.difficulty)
        self.difficulty = DIFFICULTY_ORDER[(idx + 1) % len(DIFFICULTY_ORDER)]
        self.progress.data["settings"]["difficulty"] = self.difficulty
        self.progress.save()
        self._sync_menu_items()

    def _get_menu_bg(self) -> pygame.Surface:
        """Cached dark gradient background for menu screens."""
        if self._menu_bg is None:
            surf = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
            for i in range(SCREEN_HEIGHT):
                t = i / SCREEN_HEIGHT
                r = int(30 + (60 - 30) * t)
                g = int(25 + (45 - 25) * t)
                b = int(50 + (90 - 50) * t)
                pygame.draw.line(surf, (r, g, b), (0, i), (SCREEN_WIDTH, i))
            self._menu_bg = surf
        return self._menu_bg

    def _get_scaled_bg(self, name: str) -> pygame.Surface:
        """Cached scaled background image for parallax."""
        if name not in self._bg_scaled_cache:
            bg_surf = assets.get_background(name)
            self._bg_scaled_cache[name] = pygame.transform.smoothscale(
                bg_surf, (SCREEN_WIDTH, SCREEN_HEIGHT)
            )
        return self._bg_scaled_cache[name]

    def play_sound(self, name: str):
        if self.muted:
            return
        snd = assets.get_sound(name)
        if snd:
            snd.play()

    def _load_high_score(self) -> int:
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "highscore.txt")
        try:
            with open(path, "r") as f:
                return int(f.read().strip())
        except (FileNotFoundError, ValueError):
            return 0

    def _save_high_score(self):
        self.progress.data["high_score"] = max(
            int(self.progress.data.get("high_score", 0)), self.high_score
        )
        self.progress.save()

    def _unlock_achievement(self, achievement_id: str):
        record = self.progress.unlock_achievement(achievement_id)
        if not record:
            return None
        self.level_achievements_unlocked.append(record)
        self.achievement_toasts.append({"record": record, "timer": 240})
        self.play_sound("sfx_gem")
        return record

    def _evaluate_completion_achievements(self):
        if self.current_level == len(LEVELS) - 1 and self.character_color == "beige":
            self._unlock_achievement("beige_final")
        if self.current_level == len(LEVELS) - 1 and self.difficulty == "hard":
            self._unlock_achievement("hard_victory")
        if self.current_level == 3 and getattr(self, "level_hearts_collected", 0) == 0:
            self._unlock_achievement("lava_purity")

        completed_characters = set()
        for record in self.progress.data.get("levels", {}).values():
            completed_characters.update(record.get("characters", []))
        if set(CHARACTERS).issubset(completed_characters):
            self._unlock_achievement("all_characters")

        if all(
            self.progress.level_record(i).get("badges", {}).get("exploration", False)
            for i in range(len(LEVELS))
        ):
            self._unlock_achievement("full_explorer")

    def _update_achievement_toasts(self):
        for toast in self.achievement_toasts:
            toast["timer"] -= 1
        self.achievement_toasts = [
            toast for toast in self.achievement_toasts if toast["timer"] > 0
        ]

    # ---- Level management ----
    def start_level(self, level_idx: int):
        assets.stop_music()
        self.game_over_reason = ""
        self._final_result = None
        self.current_level = level_idx
        level_data = LEVELS[level_idx]
        self.tilemap = TileMap(level_data)
        self._apply_difficulty_to_level()
        self.particles = ParticleSystem()

        # Reset stomp combo for the new level
        self._stomp_combo = 0
        self._stomp_combo_timer = 0

        # Reset slow-mo
        self.slow_mo_timer = 0
        self.fire_patches = []

        # Rebuild tutorial hints (skill hint depends on the character)
        self._build_tutorial_hints()

        # Preserve lives across levels
        initial_lives = int(self._difficulty_rules().get("initial_lives", STARTING_LIVES))
        prev_lives = self.player.lives if self.player else initial_lives

        px, py = self.tilemap.player_start
        self.player = Player(px, py, self.character_color)
        self.player.health = STARTING_HEALTH
        self.player.lives = initial_lives if level_idx == 0 else max(1, min(prev_lives, initial_lives))
        self.player.score = self.total_score

        self.camera = Camera(self.tilemap.pixel_w, self.tilemap.pixel_h)
        self.camera.x = max(0, px - SCREEN_WIDTH / 2)
        self.camera.y = max(0, py - SCREEN_HEIGHT / 2)

        self.level_time = 0.0
        self.level_deaths = 0
        self.level_enemies_defeated = 0
        self.level_skill_uses = 0
        self.level_hearts_collected = 0
        self.level_target_time = float(level_data["time_limit"])
        self.level_achievements_unlocked = []
        self._level_result = None
        self.state = self.S_PLAYING
        self.state_timer = 0

    def _apply_difficulty_to_level(self):
        """Apply parameter-only difficulty tuning to the freshly built map."""
        rules = self._difficulty_rules()
        enemy_mult = float(rules.get("enemy_speed_mult", 1.0))
        platform_mult = float(rules.get("platform_speed_mult", 1.0))
        self.tilemap.conveyor_speed_mult = float(rules.get("conveyor_speed_mult", 1.0))

        for enemy in self.tilemap.enemies:
            enemy.base_speed *= enemy_mult
            if enemy.vx:
                enemy.vx *= enemy_mult
        for platform in self.tilemap.moving_platforms:
            platform.speed *= platform_mult

        if rules.get("checkpoint_mode") == "major" and len(self.tilemap.flag_positions) > 1:
            flags = sorted(self.tilemap.flag_positions)
            self.tilemap.flag_positions = [flags[0], flags[-1]]

    def _build_tutorial_hints(self):
        """Resolve per-character hint text and reset the one-shot flags."""
        self._tutorial_hints = []
        for x_tiles, text in self._tutorial_hint_specs:
            if text == "skill":
                text = SKILL_HINTS.get(self.character_color, SKILL_HINTS["beige"])
            self._tutorial_hints.append(
                {"x": x_tiles * TILE_SIZE, "text": text, "shown": False}
            )
        self.active_tutorial_hint = None
        self.tutorial_hint_timer = 0

    def _show_hint(self, text: str, duration: int = 210):
        """Display a transient rule hint (respects the tutorial setting)."""
        if not self.show_tutorial:
            return
        self.active_tutorial_hint = text
        self.tutorial_hint_timer = duration

    def respawn_player(self):
        if self.tilemap.checkpoint:
            px, py = self.tilemap.checkpoint
        else:
            px, py = self.tilemap.player_start
        self.player.reset(px, py)
        # A failed attempt resets the guardian fight
        if self.tilemap.boss:
            self.tilemap.boss.reset()
        self.fire_patches = []
        self.player.health = STARTING_HEALTH
        self.camera.x = max(0, px - SCREEN_WIDTH / 2)
        self.camera.y = max(0, py - SCREEN_HEIGHT / 2)
        # Reset stomp combo on respawn
        self._stomp_combo = 0
        self._stomp_combo_timer = 0

    def player_died(self):
        self.level_deaths += 1
        self.player.lives -= 1
        if self.player.lives <= 0:
            self.state = self.S_GAME_OVER
            self.state_timer = 0
            if self.total_score > self.high_score:
                self.high_score = self.total_score
                self._save_high_score()
        else:
            self.respawn_player()

    def complete_level(self):
        previous_high_score = self.high_score
        target_time = max(1.0, self.level_target_time)
        time_bonus = max(0, int(500 * (1.0 - self.level_time / target_time)))
        self.total_score = self.player.score
        self.total_score += time_bonus
        self.total_time += self.level_time
        total_items = len(self.tilemap.collectibles)
        collected_items = sum(1 for item in self.tilemap.collectibles if item.collected)
        collection_ratio = collected_items / total_items if total_items else 1.0
        badges = {
            "complete": True,
            "exploration": collection_ratio >= 1.0,
            "skill": self.level_time <= target_time and self.level_deaths == 0,
        }
        stars = sum(badges.values())
        self._time_bonus = time_bonus
        self._level_result = {
            "name": self.tilemap.name,
            "time": self.level_time,
            "target_time": target_time,
            "score": self.player.score + time_bonus,
            "total_score": self.total_score,
            "collected": collected_items,
            "total_items": total_items,
            "collection_ratio": collection_ratio,
            "enemies_defeated": self.level_enemies_defeated,
            "total_enemies": len(self.tilemap.enemies),
            "deaths": self.level_deaths,
            "stars": stars,
            "badges": badges,
            "character": self.character_color,
            "difficulty": self.difficulty,
            "achievements": [],
        }
        self.progress.record_level(self.current_level, self._level_result)
        self._evaluate_completion_achievements()
        self._level_result["achievements"] = list(self.level_achievements_unlocked)
        self.high_score = max(self.high_score, int(self.progress.data["high_score"]))
        self.new_high_score = self.total_score > previous_high_score

        if self.current_level + 1 >= len(LEVELS):
            self._final_result = dict(self._level_result)
            self.state = self.S_VICTORY
            self.state_timer = 0
            if self.total_score > self.high_score:
                self.high_score = self.total_score
                self._save_high_score()
            assets.play_music("victory", muted=self.muted)
        else:
            self.state = self.S_LEVEL_COMPLETE
            self.state_timer = 0

    # ---- Main loop ----
    def run(self):
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0
            self.frame_count += 1
            self.state_timer += 1

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    self._handle_keydown(event.key)
                    if event.key == pygame.K_m:
                        self.muted = not self.muted
                        self.progress.data["settings"]["muted"] = self.muted
                        self.progress.save()
                        if self.muted:
                            assets.stop_music()
                        elif self.state == self.S_VICTORY:
                            assets.play_music("victory", muted=False)

            self._update()
            self._draw()
            pygame.display.flip()

        pygame.quit()

    # ---- Input ----
    def _handle_keydown(self, key: int):
        if self.state == self.S_MENU:
            if key in (pygame.K_UP, pygame.K_w):
                self.menu_index = (self.menu_index - 1) % len(self.menu_items)
                self.play_sound("sfx_select")
            elif key in (pygame.K_DOWN, pygame.K_s):
                self.menu_index = (self.menu_index + 1) % len(self.menu_items)
                self.play_sound("sfx_select")
            elif key in (pygame.K_RETURN, pygame.K_SPACE):
                self._menu_action()
            elif key == pygame.K_ESCAPE:
                pygame.event.post(pygame.event.Event(pygame.QUIT))

        elif self.state == self.S_CONTROLS:
            if key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                self.state = self.S_MENU
            elif key == pygame.K_t:
                # Accessibility: tutorial hints can be turned off
                self.show_tutorial = not self.show_tutorial
                self.progress.data["settings"]["tutorial_hints"] = self.show_tutorial
                self.progress.save()
                self.play_sound("sfx_select")

        elif self.state == self.S_CHARSELECT:
            if key in (pygame.K_LEFT, pygame.K_a):
                self.char_index = (self.char_index - 1) % len(CHARACTERS)
                self.play_sound("sfx_select")
            elif key in (pygame.K_RIGHT, pygame.K_d):
                self.char_index = (self.char_index + 1) % len(CHARACTERS)
                self.play_sound("sfx_select")
            elif key in (pygame.K_RETURN, pygame.K_SPACE):
                self.character_color = CHARACTERS[self.char_index]
                self.state = self.S_MENU
                self.play_sound("sfx_gem")
            elif key == pygame.K_ESCAPE:
                self.state = self.S_MENU

        elif self.state == self.S_LEVEL_SELECT:
            unlocked = int(self.progress.data.get("unlocked_level", 0))
            if key in (pygame.K_LEFT, pygame.K_a):
                self.level_select_index = max(0, self.level_select_index - 1)
                self.play_sound("sfx_select")
            elif key in (pygame.K_RIGHT, pygame.K_d):
                self.level_select_index = min(
                    min(unlocked, len(LEVELS) - 1), self.level_select_index + 1
                )
                self.play_sound("sfx_select")
            elif key in (pygame.K_RETURN, pygame.K_SPACE):
                if self.level_select_index <= unlocked:
                    self.total_score = 0
                    self.total_time = 0
                    self.player = None
                    self.start_level(self.level_select_index)
                    self.play_sound("sfx_gem")
            elif key == pygame.K_ESCAPE:
                self.state = self.S_MENU

        elif self.state == self.S_PLAYING:
            if key in (pygame.K_SPACE, pygame.K_z, pygame.K_j, pygame.K_UP, pygame.K_w):
                self.player.try_jump(self.tilemap, self.play_sound)
            elif key in (pygame.K_x,):
                activated = self.player.try_skill(
                    self, self.tilemap, self.tilemap.enemies,
                    self.particles, self.play_sound,
                )
                if activated:
                    self.level_skill_uses += 1
            elif key in (pygame.K_c,):
                activated = self.player.try_skill(
                    self, self.tilemap, self.tilemap.enemies,
                    self.particles, self.play_sound,
                )
                if activated:
                    self.level_skill_uses += 1
            elif key == pygame.K_ESCAPE:
                self.state = self.S_PAUSED
                self.state_timer = 0

        elif self.state == self.S_PAUSED:
            if key == pygame.K_ESCAPE or key == pygame.K_p:
                self.state = self.S_PLAYING
            elif key == pygame.K_r:
                self.start_level(self.current_level)
            elif key == pygame.K_q:
                self.state = self.S_MENU
                self.state_timer = 0

        elif self.state == self.S_LEVEL_COMPLETE:
            if key in (pygame.K_RETURN, pygame.K_SPACE):
                self.start_level(self.current_level + 1)
            elif key == pygame.K_ESCAPE:
                self.state = self.S_MENU

        elif self.state == self.S_GAME_OVER:
            if key in (pygame.K_RETURN, pygame.K_SPACE):
                self.total_score = 0
                self.total_time = 0
                self.start_level(0)
            elif key == pygame.K_ESCAPE:
                self.state = self.S_MENU
                self.total_score = 0

        elif self.state == self.S_VICTORY:
            if key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_ESCAPE):
                assets.stop_music()
                self.state = self.S_MENU
                self.total_score = 0
                self.total_time = 0

    def _menu_action(self):
        action = self.menu_items[self.menu_index]
        self.play_sound("sfx_gem")
        if action == "Start Game":
            self.total_score = 0
            self.total_time = 0
            self.start_level(0)
        elif action == "Select Character":
            self.state = self.S_CHARSELECT
        elif action == "Controls":
            self.state = self.S_CONTROLS
        elif action == "Level Select":
            self.level_select_index = min(
                self.level_select_index,
                int(self.progress.data.get("unlocked_level", 0)),
            )
            self.state = self.S_LEVEL_SELECT
        elif action.startswith("Difficulty:"):
            self._cycle_difficulty()
            self.play_sound("sfx_select")
        elif action == "Quit":
            pygame.event.post(pygame.event.Event(pygame.QUIT))

    # ---- Update ----
    def _update(self):
        if self.state == self.S_PLAYING:
            self._update_playing()
        elif self.state == self.S_LEVEL_COMPLETE:
            if self.state_timer > 600:  # auto-advance after 10s
                self.start_level(self.current_level + 1)
        self._update_achievement_toasts()

    def _on_enemy_defeated(self, enemy, method: str):
        """Apply scoring, statistics, and feedback for every kill path."""
        self.level_enemies_defeated += 1
        color = WHITE
        if method == "stomp":
            self._stomp_combo = getattr(self, "_stomp_combo", 0) + 1
            points = 30 * self._stomp_combo
            self._stomp_combo_timer = 120
            color = YELLOW if self._stomp_combo > 1 else WHITE
            label = f"+{points}"
            if self._stomp_combo > 1:
                label += f"  x{self._stomp_combo}!"
            self.play_sound("sfx_bump")
            if self._stomp_combo >= 3:
                self._unlock_achievement("combo_master")
        elif method == "dash":
            if enemy.etype == "spike_slime":
                # Armoured enemy broken: louder, clearer reward.
                points = 100
                color = ORANGE
                label = "+100 ARMOR BREAK!"
            else:
                points = 50
                color = GREEN
                label = "+50 DASH"
            self.play_sound("sfx_disappear")
        elif method == "shell":
            points = 50
            color = LIGHT_GRAY
            label = "+50 SHELL"
            self.play_sound("sfx_disappear")
        else:
            if enemy.etype == "spike_slime":
                points = 100
                color = ORANGE
                label = "+100 ARMOR BREAK!"
            else:
                points = 50
                color = GOLD
                label = "+50 STAR"
            self.play_sound("sfx_disappear")
        self.player.score += points
        self.particles.emit_burst(
            enemy.x + enemy.size / 2, enemy.y + enemy.size / 2,
            color, count=14, speed=4, size=4, life=25,
        )
        self.particles.emit_float_text(
            enemy.x + enemy.size / 2, enemy.y, label, color
        )
        if enemy.etype == "fire_slime" and method == "stomp":
            self.fire_patches.append(FirePatch(enemy.x, enemy.y + enemy.size))

    def _update_playing(self):
        self.level_time += 1 / FPS
        if self._difficulty_rules().get("countdown") and self.level_time >= self.level_target_time:
            self.game_over_reason = "TIME UP"
            self.state = self.S_GAME_OVER
            self.state_timer = 0
            if self.total_score > self.high_score:
                self.high_score = self.total_score
                self._save_high_score()
            return
        keys = pygame.key.get_pressed()

        # Level 1 tutorial triggers (each fires once, can be disabled)
        if self.current_level == 0 and self.show_tutorial:
            for hint in self._tutorial_hints:
                if not hint["shown"] and self.player.x >= hint["x"]:
                    hint["shown"] = True
                    self._show_hint(hint["text"], 180)
        if self.tutorial_hint_timer > 0:
            self.tutorial_hint_timer -= 1
            if self.tutorial_hint_timer == 0:
                self.active_tutorial_hint = None

        # Update player
        self.player.update(keys, self.tilemap, self.particles, self.play_sound)

        # Update skill (dash enemy kills, etc.)
        self.player.update_skill(
            self.tilemap, self.tilemap.enemies, self.particles,
            self.play_sound, self._on_enemy_defeated,
        )

        # Camera
        self.camera.update(self.player.center_x, self.player.center_y)

        # Update enemies and moving platforms (with slow-mo effect).
        # Slow-mo stretches the *danger rhythm* of active machinery to 25%
        # speed, matching how enemies are slowed.
        slow_mo_active = self.slow_mo_timer > 0
        if slow_mo_active:
            self.slow_mo_timer -= 1
            # Only update enemies every 4th frame (25% speed)
            if self.frame_count % 4 == 0:
                for enemy in self.tilemap.enemies:
                    enemy.update(self.tilemap)
            if self.slow_mo_timer <= 0:
                self.player.skill_active = False
        else:
            for enemy in self.tilemap.enemies:
                enemy.update(self.tilemap)

        # Update collectibles
        for item in self.tilemap.collectibles:
            item.update()

        # Update moving platforms (frozen on 3 of 4 slow-mo frames)
        platforms_active = not slow_mo_active or self.frame_count % 4 == 0
        for mp in self.tilemap.moving_platforms:
            mp.update(platforms_active)

        # Fire patches: slow-mo stretches the warning only, never the burn.
        slow_warning = slow_mo_active and self.frame_count % 4 != 0
        for patch in self.fire_patches:
            patch.update(slow_warning)
            if patch.dangerous and self.player.rect.colliderect(patch.rect):
                if self.player.take_hazard_hit(self.particles, self.play_sound):
                    self.player.vx *= -0.5
        # Extinguished patches puff out a small cloud of smoke
        for patch in self.fire_patches:
            if not patch.alive:
                self.particles.emit_burst(
                    patch.rect.centerx, patch.rect.top, (160, 160, 160),
                    count=6, speed=1.5, size=4, life=25, gravity=-0.05,
                )
        self.fire_patches = [patch for patch in self.fire_patches if patch.alive]

        # ---- Block guardian (frozen on pause; stretched by slow-mo) ----
        if self.tilemap.boss:
            if not slow_mo_active or self.frame_count % 4 == 0:
                self.tilemap.boss.update(
                    self.player, self.particles, self.play_sound, self.camera
                )
            if self.tilemap.boss.defeated and not self.tilemap.door_open:
                self.tilemap.open_door()
                self.particles.emit_float_text(
                    self.tilemap.boss.center_x, self.tilemap.boss.floor_top - 80,
                    "The way is open!", GOLD
                )

        # Update spring timers
        for key in list(self.tilemap.spring_timers.keys()):
            self.tilemap.spring_timers[key] -= 1
            if self.tilemap.spring_timers[key] <= 0:
                del self.tilemap.spring_timers[key]

        # Update particles
        self.particles.update()

        # ---- Collisions: player vs collectibles ----
        for item in self.tilemap.collectibles:
            if not item.collected and self.player.rect.colliderect(item.draw_rect):
                item.collected = True
                self.player.score += item.score
                if item.kind in "oO0":
                    self.player.coins += 1
                elif item.kind in "bgry":
                    self.player.gems += 1
                elif item.kind == "H":
                    self.player.health = min(self.player.max_health, self.player.health + item.heal)
                    self.level_hearts_collected += 1
                elif item.kind == "*":
                    # Star grants invincibility
                    self.player.activate_star(self.particles, self.play_sound)
                    if not self._star_hint_shown:
                        self._star_hint_shown = True
                        self._show_hint(STAR_RULE_HINT)
                elif item.kind == "c":
                    self.player.reset_skill_cooldown()
                self.play_sound(item.sound_name)
                self.particles.emit_burst(
                    item.x + item.size / 2, item.y + item.size / 2,
                    item.color, count=10, speed=3, size=4, life=25
                )
                # Floating score text
                if item.score > 0:
                    self.particles.emit_float_text(
                        item.x + item.size / 2, item.y,
                        f"+{item.score}", item.color
                    )

        # ---- Collisions: player vs enemies ----
        for enemy in self.tilemap.enemies:
            if not enemy.alive:
                continue
            if self.player.rect.colliderect(enemy.hitbox):
                # Star invincibility: kill any killable enemy on contact
                # (armoured spike slimes included; saws never).
                if self.player.star_invincible > 0 and enemy.dashable:
                    enemy.kill()
                    self._on_enemy_defeated(enemy, "star")
                    continue
                # Check if stomping (falling and feet were above enemy center)
                stomp = (self.player.vy > 0 and
                         self.player.prev_feet_y <= enemy.hitbox.centery + 4)
                if stomp and enemy.stompable:
                    enemy.stomp()
                    self.player.vy = JUMP_VELOCITY * 0.7  # bounce
                    self.player.jumping = True
                    self.player.on_ground = False
                    if not enemy.alive:
                        self._on_enemy_defeated(enemy, "stomp")
                    else:
                        self.play_sound("sfx_bump")
                elif enemy.etype == "snail" and enemy.in_shell \
                        and abs(enemy.vx) < 1.5:
                    # Kick a stationary shell instead of taking damage.
                    direction = 1 if self.player.center_x < enemy.x + enemy.size / 2 else -1
                    if enemy.kick(direction):
                        self.play_sound("sfx_bump")
                        self.particles.emit_burst(
                            enemy.x + enemy.size / 2, enemy.y + enemy.size / 2,
                            LIGHT_GRAY, count=8, speed=3, size=4, life=20,
                        )
                else:
                    if self.player.take_damage():
                        # Knockback away from enemy
                        dx = self.player.center_x - (enemy.x + enemy.size / 2)
                        self.player.vx = 6 if dx > 0 else -6
                        self.play_sound("sfx_hurt")
                        self.camera.shake(8, 15)
                        self.particles.emit_burst(
                            self.player.center_x, self.player.center_y,
                            RED, count=16, speed=5, size=5, life=30
                        )

        # ---- Kicked shells defeat the first enemy they hit ----
        for shell in self.tilemap.enemies:
            if not (shell.alive and shell.etype == "snail"
                    and shell.in_shell and abs(shell.vx) >= 1.5):
                continue
            for other in self.tilemap.enemies:
                if other is shell or not other.alive:
                    continue
                if shell.hitbox.colliderect(other.hitbox):
                    other.kill()
                    self._on_enemy_defeated(other, "shell")
                    shell.vx *= 0.2  # chain damage limited: shell nearly stops
                    break

        # ---- Collisions: player vs keys ----
        if not self.tilemap.has_key:
            for (col, row) in self.tilemap.key_positions:
                key_rect = pygame.Rect(col * TILE_SIZE, row * TILE_SIZE, TILE_SIZE, TILE_SIZE)
                if self.player.rect.colliderect(key_rect):
                    self.tilemap.collect_key()
                    self.play_sound("sfx_gem")
                    self.show_key_msg = 120
                    self.particles.emit_burst(
                        col * TILE_SIZE + TILE_SIZE / 2, row * TILE_SIZE + TILE_SIZE / 2,
                        YELLOW, count=20, speed=5, size=5, life=35
                    )

        # ---- Collisions: player vs flags (checkpoints) ----
        for (col, row) in self.tilemap.flag_positions:
            flag_rect = pygame.Rect(col * TILE_SIZE, row * TILE_SIZE, TILE_SIZE, TILE_SIZE)
            if self.player.rect.colliderect(flag_rect):
                new_cp = (col * TILE_SIZE, row * TILE_SIZE)
                if self.tilemap.checkpoint != new_cp:
                    self.tilemap.checkpoint = new_cp
                    self.play_sound("sfx_select")
                    self.particles.emit_burst(
                        col * TILE_SIZE + TILE_SIZE / 2, row * TILE_SIZE + TILE_SIZE / 2,
                        YELLOW, count=12, speed=3, size=4, life=25
                    )

        # ---- Collisions: player vs door ----
        if self.tilemap.door_pos:
            dcol, drow = self.tilemap.door_pos
            door_rect = pygame.Rect(
                dcol * TILE_SIZE, drow * TILE_SIZE,
                TILE_SIZE, TILE_SIZE * 2,
            )
            if self.player.rect.colliderect(door_rect):
                # Need key if there are locks; the guardian seals its door.
                has_locks = len(self.tilemap.locks) > 0
                boss_ok = self.tilemap.boss is None or self.tilemap.boss.defeated
                if (not has_locks or self.tilemap.locks_open) and boss_ok:
                    self.tilemap.open_door()
                    self.complete_level()
                    self.play_sound("sfx_magic")
                elif not boss_ok and self.door_sealed_msg <= 0:
                    self.door_sealed_msg = 150
                    self.play_sound("sfx_hurt")

        # ---- Fall death ----
        if self.player.y > self.tilemap.pixel_h + 100:
            if self.player.take_damage(ignore_star=True):
                self.play_sound("sfx_hurt")
            if self.player.health <= 0:
                self.player_died()
            else:
                self.respawn_player()

        # ---- Health death ----
        if self.player.health <= 0:
            self.player_died()

        if self.show_key_msg > 0:
            self.show_key_msg -= 1
        if self.door_sealed_msg > 0:
            self.door_sealed_msg -= 1

        # Stomp combo timer
        if hasattr(self, '_stomp_combo_timer') and self._stomp_combo_timer > 0:
            self._stomp_combo_timer -= 1
            if self._stomp_combo_timer <= 0:
                self._stomp_combo = 0

    # ---- Draw ----
    def _draw(self):
        if self.state == self.S_MENU:
            self._draw_menu()
        elif self.state == self.S_CHARSELECT:
            self._draw_charselect()
        elif self.state == self.S_LEVEL_SELECT:
            self._draw_level_select()
        elif self.state == self.S_CONTROLS:
            self._draw_controls()
        elif self.state == self.S_PLAYING:
            self._draw_playing()
        elif self.state == self.S_PAUSED:
            self._draw_playing()
            self._draw_paused_overlay()
        elif self.state == self.S_LEVEL_COMPLETE:
            self._draw_playing()
            self._draw_level_complete()
        elif self.state == self.S_GAME_OVER:
            self._draw_game_over()
        elif self.state == self.S_VICTORY:
            self._draw_victory()
        if self.achievement_toasts:
            self._draw_achievement_toasts()

    def _draw_background(self, cam: Camera):
        """Draw sky gradient + parallax background images."""
        theme = LEVEL_THEMES.get(self.tilemap.theme, LEVEL_THEMES["grass"])

        # Sky gradient (cached per theme)
        cache_key = f"sky:{self.tilemap.theme}"
        if cache_key not in self._sky_cache:
            surf = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
            top = theme["sky_top"]
            bot = theme["sky_bot"]
            for i in range(SCREEN_HEIGHT):
                t = i / SCREEN_HEIGHT
                r = int(top[0] + (bot[0] - top[0]) * t)
                g = int(top[1] + (bot[1] - top[1]) * t)
                b = int(top[2] + (bot[2] - top[2]) * t)
                pygame.draw.line(surf, (r, g, b), (0, i), (SCREEN_WIDTH, i))
            self._sky_cache[cache_key] = surf
        self.screen.blit(self._sky_cache[cache_key], (0, 0))

        # Far background (parallax 0.3)
        bg_far_name = theme.get("bg_far")
        if bg_far_name:
            try:
                bg_scaled = self._get_scaled_bg(bg_far_name)
                ox = -cam.x * 0.3 % SCREEN_WIDTH
                self.screen.blit(bg_scaled, (ox - SCREEN_WIDTH, 0))
                self.screen.blit(bg_scaled, (int(ox), 0))
            except Exception:
                pass

        # Near background (parallax 0.6)
        bg_near_name = theme.get("bg_image")
        if bg_near_name:
            try:
                bg_scaled = self._get_scaled_bg(bg_near_name)
                ox = -cam.x * 0.6 % SCREEN_WIDTH
                self.screen.blit(bg_scaled, (ox - SCREEN_WIDTH, 0))
                self.screen.blit(bg_scaled, (int(ox), 0))
            except Exception:
                pass

    def _draw_playing(self):
        self._draw_background(self.camera)

        # Static tiles
        self.tilemap.draw_static(self.screen, self.camera)

        # Animated tiles
        self.tilemap.draw_animated(self.screen, self.camera, self.frame_count)

        # Moving platforms
        for mp in self.tilemap.moving_platforms:
            mp.draw(self.screen, self.camera)

        # Collectibles
        for item in self.tilemap.collectibles:
            item.draw(self.screen, self.camera)

        # Enemies
        for enemy in self.tilemap.enemies:
            enemy.draw(self.screen, self.camera)

        # Block guardian (and its shockwaves)
        if self.tilemap.boss:
            self.tilemap.boss.draw(self.screen, self.camera, self.frame_count)

        for patch in self.fire_patches:
            patch.draw(self.screen, self.camera, self.frame_count)

        # Player
        self.player.draw(self.screen, self.camera)

        # Particles
        self.particles.draw(self.screen, self.camera)

        # HUD
        self._draw_hud()

        # Level intro overlay (first 120 frames)
        if self.state_timer < 120:
            alpha = 255
            if self.state_timer < 15:
                alpha = int(255 * self.state_timer / 15)
            elif self.state_timer > 90:
                alpha = int(255 * (120 - self.state_timer) / 30)
            intro = self.font_big.render(
                f"Level {self.current_level + 1}", True, WHITE
            )
            name = self.font_med.render(self.tilemap.name, True, GOLD)
            intro.set_alpha(alpha)
            name.set_alpha(alpha)
            self.screen.blit(intro, intro.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 30)))
            self.screen.blit(name, name.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 20)))

    def _draw_hud(self):
        # Hearts
        heart_full = assets.get_tile_scaled("hud_heart", 32)
        heart_empty = assets.get_tile_scaled("hud_heart_empty", 32)
        player_max_hp = self.player.max_health
        for i in range(player_max_hp):
            x = 15 + i * 34
            y = 12
            img = heart_full if i < self.player.health else heart_empty
            self.screen.blit(img, (x, y))

        # Lives
        lives_text = self.font_small.render(f"x{self.player.lives}", True, WHITE)
        self.screen.blit(lives_text, (15 + player_max_hp * 34 + 5, 18))

        # Coins
        coin_icon = assets.get_tile_scaled("hud_coin", 28)
        self.screen.blit(coin_icon, (SCREEN_WIDTH // 2 - 50, 14))
        coin_text = self.font_med.render(f"{self.player.coins}", True, WHITE)
        self.screen.blit(coin_text, (SCREEN_WIDTH // 2 - 18, 14))

        # Score
        score_text = self.font_med.render(f"{self.player.score:06d}", True, WHITE)
        self.screen.blit(score_text, (SCREEN_WIDTH - score_text.get_width() - 15, 14))

        # Level name + timer
        level_text = self.font_small.render(
            f"Level {self.current_level + 1}: {self.tilemap.name}", True, WHITE
        )
        self.screen.blit(level_text, (15, SCREEN_HEIGHT - 30))
        target = getattr(self, "level_target_time", 0)
        if self._difficulty_rules().get("countdown"):
            remaining = max(0.0, target - self.level_time)
            time_color = RED if remaining <= 10 else YELLOW
            timer_label = f"Hard: {remaining:.1f}s left"
        else:
            time_color = WHITE if self.level_time <= target else ORANGE
            timer_label = f"Time: {self.level_time:.1f}s / {target:.0f}s"
        time_text = self.font_small.render(timer_label, True, time_color)
        self.screen.blit(time_text, (SCREEN_WIDTH - time_text.get_width() - 15, SCREEN_HEIGHT - 30))

        # Key indicator
        if self.tilemap.has_key:
            key_icon = assets.get_tile_scaled("hud_key_yellow", 28)
            self.screen.blit(key_icon, (SCREEN_WIDTH // 2 + 40, 14))

        # Collectible progress
        total_items = len(self.tilemap.collectibles)
        collected_items = sum(1 for c in self.tilemap.collectibles if c.collected)
        if total_items > 0:
            progress_text = self.font_tiny.render(
                f"Items: {collected_items}/{total_items}", True, LIGHT_GRAY
            )
            self.screen.blit(progress_text, (SCREEN_WIDTH // 2 + 80, 18))

        # Combo indicator
        combo = getattr(self, '_stomp_combo', 0)
        if combo > 1:
            combo_text = self.font_med.render(f"COMBO x{combo}!", True, YELLOW)
            alpha = min(255, getattr(self, '_stomp_combo_timer', 0) * 3)
            combo_text.set_alpha(alpha)
            self.screen.blit(combo_text, combo_text.get_rect(center=(SCREEN_WIDTH // 2, 60)))

        # Key collected message
        if self.show_key_msg > 0:
            alpha = min(255, self.show_key_msg * 4) if self.show_key_msg < 30 else 255
            msg = self.font_med.render("Key Collected! Locks Opened!", True, YELLOW)
            msg.set_alpha(alpha)
            rect = msg.get_rect(center=(SCREEN_WIDTH // 2, 80))
            self.screen.blit(msg, rect)

        # Guardian-sealed door message
        if self.door_sealed_msg > 0:
            alpha = min(255, self.door_sealed_msg * 4) if self.door_sealed_msg < 30 else 255
            msg = self.font_med.render("The Guardian seals the door!", True, RED)
            msg.set_alpha(alpha)
            rect = msg.get_rect(center=(SCREEN_WIDTH // 2, 80))
            self.screen.blit(msg, rect)

        # Mute indicator
        if self.muted:
            mute_text = self.font_tiny.render("MUTED (M)", True, LIGHT_GRAY)
            self.screen.blit(mute_text, (SCREEN_WIDTH - mute_text.get_width() - 15, 50))

        # Skill cooldown indicator (bottom-left)
        from src.constants import CHARACTER_SKILLS
        skill_info = CHARACTER_SKILLS.get(self.player.color, {})
        skill_name = skill_info.get("name", "")
        if skill_name:
            max_cd = skill_info.get("cooldown", 0)
            if max_cd > 0:
                cd_frac = 1.0 - (self.player.skill_cooldown / max_cd) if max_cd > 0 else 1.0
                cd_color = GREEN if self.player.skill_cooldown == 0 else GRAY
                cd_text = self.font_tiny.render(
                    f"{skill_name}: {'READY' if self.player.skill_cooldown == 0 else f'{self.player.skill_cooldown // 60 + 1}s'}",
                    True, cd_color
                )
                self.screen.blit(cd_text, (15, SCREEN_HEIGHT - 55))
                # Cooldown bar
                bar_w = 120
                bar_h = 6
                bar_x = 15
                bar_y = SCREEN_HEIGHT - 40
                pygame.draw.rect(self.screen, DARK_GRAY, (bar_x, bar_y, bar_w, bar_h))
                pygame.draw.rect(self.screen, cd_color, (bar_x, bar_y, int(bar_w * cd_frac), bar_h))
            else:
                # No-cooldown skill (double jump)
                dj_color = YELLOW if self.player.double_jumps_left > 0 else GRAY
                dj_text = self.font_tiny.render(
                    f"{skill_name}: {'READY' if self.player.double_jumps_left > 0 else 'USED'}",
                    True, dj_color
                )
                self.screen.blit(dj_text, (15, SCREEN_HEIGHT - 55))

        # Star invincibility timer
        if self.player.star_invincible > 0:
            star_text = self.font_small.render(
                f"STAR {self.player.star_invincible // 60 + 1}s", True, GOLD
            )
            self.screen.blit(star_text, (SCREEN_WIDTH // 2 - star_text.get_width() // 2, 50))

        # Slow-mo timer overlay
        if self.slow_mo_timer > 0:
            overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            edge_alpha = min(40, self.slow_mo_timer)
            overlay.fill((160, 80, 220, edge_alpha))
            self.screen.blit(overlay, (0, 0))
            sm_text = self.font_small.render(
                f"SLOW MO {self.slow_mo_timer // 60 + 1}s", True, PURPLE
            )
            self.screen.blit(sm_text, sm_text.get_rect(center=(SCREEN_WIDTH // 2, 75)))

        # Tutorial / rule hints (triggered in any level)
        if self.active_tutorial_hint:
            hint_text = self.font_small.render(self.active_tutorial_hint, True, YELLOW)
            hint_text.set_alpha(min(220, self.tutorial_hint_timer * 5))
            self.screen.blit(
                hint_text,
                hint_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 80)),
            )

    # ---- Menu screens ----
    def _draw_menu(self):
        # Cached gradient background
        self.screen.blit(self._get_menu_bg(), (0, 0))

        # Decorative background tiles (cached)
        bg_scaled = self._get_scaled_bg("background_color_trees").copy()
        bg_scaled.set_alpha(60)
        self.screen.blit(bg_scaled, (0, 0))

        # Title
        title = self.font_big.render("ZENO'S ADVENTURE", True, GOLD)
        title_rect = title.get_rect(center=(SCREEN_WIDTH // 2, 130))
        # Shadow
        shadow = self.font_big.render("ZENO'S ADVENTURE", True, BLACK)
        self.screen.blit(shadow, (title_rect.x + 3, title_rect.y + 3))
        self.screen.blit(title, title_rect)

        subtitle = self.font_small.render("A Platformer Adventure", True, LIGHT_GRAY)
        self.screen.blit(subtitle, subtitle.get_rect(center=(SCREEN_WIDTH // 2, 175)))

        # Menu items
        for i, item in enumerate(self.menu_items):
            y = 230 + i * 42
            color = YELLOW if i == self.menu_index else WHITE
            text = self.font_med.render(item, True, color)
            rect = text.get_rect(center=(SCREEN_WIDTH // 2, y))
            if i == self.menu_index:
                # Draw selection indicator
                arrow = self.font_med.render(">", True, YELLOW)
                self.screen.blit(arrow, (rect.x - 30, rect.y))
            self.screen.blit(text, rect)

        # Character preview
        char_idle = assets.load_character_set(self.character_color, 0.8)["idle"][0]
        char_rect = char_idle.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 90))
        self.screen.blit(char_idle, char_rect)
        char_label = self.font_small.render(f"Character: {self.character_color.title()}", True, LIGHT_GRAY)
        self.screen.blit(char_label, char_label.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 45)))

        # High score
        if self.high_score > 0:
            hs_text = self.font_small.render(f"High Score: {self.high_score:06d}", True, GOLD)
            self.screen.blit(hs_text, (15, SCREEN_HEIGHT - 30))

        # Instructions
        hint = self.font_tiny.render("Arrow Keys/WASD: Navigate   Enter: Select   ESC: Quit", True, GRAY)
        self.screen.blit(hint, hint.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 15)))

    def _draw_charselect(self):
        # Cached background
        self.screen.blit(self._get_menu_bg(), (0, 0))

        title = self.font_big.render("SELECT CHARACTER", True, GOLD)
        self.screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 100)))

        # Show all characters with skill descriptions
        spacing = SCREEN_WIDTH // (len(CHARACTERS) + 1)
        for i, color in enumerate(CHARACTERS):
            x = spacing * (i + 1)
            y = SCREEN_HEIGHT // 2 - 20
            frames = assets.load_character_set(color, 1.0)
            sprite = frames["idle"][0]
            if i == self.char_index:
                # Highlight
                pygame.draw.rect(self.screen, YELLOW,
                                 (x - 96, y - 80, 192, 220), 3, border_radius=6)
                # Bounce effect
                y += math.sin(self.frame_count * 0.1) * 5
            self.screen.blit(sprite, sprite.get_rect(center=(x, y)))

            # Character name
            label = self.font_small.render(color.title(), True,
                                           WHITE if i != self.char_index else YELLOW)
            self.screen.blit(label, label.get_rect(center=(x, y + 70)))

            # Skill name
            from src.constants import CHARACTER_SKILLS
            skill_info = CHARACTER_SKILLS.get(color, {})
            skill_name = skill_info.get("name", "")
            skill_desc = skill_info.get("desc", "")
            name_text = self.font_tiny.render(skill_name, True,
                                              YELLOW if i == self.char_index else LIGHT_GRAY)
            self.screen.blit(name_text, name_text.get_rect(center=(x, y + 90)))
            desc_text = self.font_tiny.render(skill_desc, True, LIGHT_GRAY)
            self.screen.blit(desc_text, desc_text.get_rect(center=(x, y + 108)))

        hint = self.font_small.render("Left/Right: Choose   Enter: Confirm   ESC: Back", True, LIGHT_GRAY)
        self.screen.blit(hint, hint.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 60)))

    def _draw_level_select(self):
        self.screen.blit(self._get_menu_bg(), (0, 0))
        title = self.font_big.render("LEVEL SELECT", True, GOLD)
        self.screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 95)))

        unlocked = int(self.progress.data.get("unlocked_level", 0))
        card_w = 180
        gap = 14
        total_w = len(LEVELS) * card_w + (len(LEVELS) - 1) * gap
        start_x = (SCREEN_WIDTH - total_w) // 2
        for i, level in enumerate(LEVELS):
            x = start_x + i * (card_w + gap)
            selected = i == self.level_select_index
            available = i <= unlocked
            border = YELLOW if selected else GRAY
            fill = (45, 42, 65) if available else (28, 27, 38)
            pygame.draw.rect(self.screen, fill, (x, 205, card_w, 220), border_radius=6)
            pygame.draw.rect(
                self.screen, border, (x, 205, card_w, 220),
                3 if selected else 1, border_radius=6,
            )
            number = self.font_med.render(str(i + 1), True, WHITE if available else GRAY)
            self.screen.blit(number, number.get_rect(center=(x + card_w // 2, 245)))
            name = self.font_tiny.render(level["name"], True, WHITE if available else GRAY)
            self.screen.blit(name, name.get_rect(center=(x + card_w // 2, 290)))

            record = self.progress.level_record(i)
            stars = int(record.get("stars", 0)) if available else 0
            stars_text = self.font_med.render(
                " ".join("*" if n < stars else "-" for n in range(3)),
                True, GOLD if available else GRAY,
            )
            self.screen.blit(stars_text, stars_text.get_rect(center=(x + card_w // 2, 335)))
            if record:
                best = self.font_tiny.render(
                    f"Best {float(record['best_time']):.1f}s", True, LIGHT_GRAY
                )
                self.screen.blit(best, best.get_rect(center=(x + card_w // 2, 380)))
            elif not available:
                locked = self.font_tiny.render("LOCKED", True, GRAY)
                self.screen.blit(locked, locked.get_rect(center=(x + card_w // 2, 380)))

        hint = self.font_small.render(
            "Left/Right: Choose   Enter: Play   ESC: Back", True, LIGHT_GRAY
        )
        self.screen.blit(hint, hint.get_rect(center=(SCREEN_WIDTH // 2, 500)))

    def _draw_controls(self):
        # Cached background
        self.screen.blit(self._get_menu_bg(), (0, 0))

        title = self.font_big.render("CONTROLS", True, GOLD)
        self.screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 100)))

        controls = [
            ("Move Left/Right", "Arrow Keys / A, D"),
            ("Jump", "Space / Z / J / Up / W"),
            ("Duck", "Down / S"),
            ("Climb Ladder", "Up / W (on ladder)"),
            ("Use Skill", "X (Dash) / C (Slow) / Space (Double Jump)"),
            ("Pause", "ESC"),
            ("Mute Sound", "M"),
            ("Stomp Enemies", "Jump on them from above"),
            ("Collect Items", "Walk into coins, gems, hearts"),
            ("Find the Key", "Unlocks the door"),
            ("Reach the Door", "Complete the level"),
        ]

        y = 175
        for action, keys in controls:
            a_text = self.font_small.render(action, True, LIGHT_GRAY)
            k_text = self.font_small.render(keys, True, WHITE)
            self.screen.blit(a_text, (SCREEN_WIDTH // 2 - 200, y))
            self.screen.blit(k_text, (SCREEN_WIDTH // 2 + 20, y))
            y += 34

        toggle_state = "ON" if self.show_tutorial else "OFF"
        toggle = self.font_small.render(
            f"Tutorial Hints: {toggle_state}  (press T to toggle)", True, GREEN
        )
        self.screen.blit(toggle, toggle.get_rect(center=(SCREEN_WIDTH // 2, y + 10)))

        diff = self._difficulty_rules()
        diff_text = self.font_tiny.render(
            f"Difficulty: {diff['label']} — change from main menu", True, LIGHT_GRAY
        )
        self.screen.blit(diff_text, diff_text.get_rect(center=(SCREEN_WIDTH // 2, y + 40)))

        hint = self.font_small.render("Press ESC or Enter to go back", True, YELLOW)
        self.screen.blit(hint, hint.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 50)))

    def _draw_paused_overlay(self):
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        self.screen.blit(overlay, (0, 0))

        title = self.font_big.render("PAUSED", True, WHITE)
        self.screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 220)))

        items = ["ESC: Resume", "R: Restart Level", "Q: Quit to Menu"]
        for i, item in enumerate(items):
            text = self.font_med.render(item, True, LIGHT_GRAY)
            self.screen.blit(text, text.get_rect(center=(SCREEN_WIDTH // 2, 320 + i * 50)))

    def _draw_level_complete(self):
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        alpha = min(200, self.state_timer * 8)
        overlay.fill((0, 0, 0, alpha))
        self.screen.blit(overlay, (0, 0))

        if self.state_timer < 15:
            return

        title = self.font_big.render("LEVEL COMPLETE!", True, GREEN)
        self.screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 180)))

        result = self._level_result or {}
        stars = int(result.get("stars", 1))
        star_text = self.font_big.render(
            " ".join("*" if i < stars else "-" for i in range(3)), True, GOLD
        )
        self.screen.blit(star_text, star_text.get_rect(center=(SCREEN_WIDTH // 2, 250)))

        score_text = self.font_med.render(f"Score: {self.total_score:06d}", True, WHITE)
        self.screen.blit(score_text, score_text.get_rect(center=(SCREEN_WIDTH // 2, 300)))

        time_bonus = getattr(self, "_time_bonus", 0)
        bonus_text = self.font_med.render(f"Time Bonus: +{time_bonus}", True, YELLOW)
        self.screen.blit(bonus_text, bonus_text.get_rect(center=(SCREEN_WIDTH // 2, 352)))

        stats_text = self.font_small.render(
            f"Items {result.get('collected', 0)}/{result.get('total_items', 0)}"
            f"   Enemies {result.get('enemies_defeated', 0)}/{result.get('total_enemies', 0)}"
            f"   Deaths {result.get('deaths', 0)}",
            True, LIGHT_GRAY,
        )
        self.screen.blit(stats_text, stats_text.get_rect(center=(SCREEN_WIDTH // 2, 400)))

        achievements = result.get("achievements", [])
        if achievements:
            names = ", ".join(a["name"] for a in achievements[:3])
            ach_text = self.font_small.render(f"Achievement unlocked: {names}", True, GOLD)
            self.screen.blit(ach_text, ach_text.get_rect(center=(SCREEN_WIDTH // 2, 440)))
            next_y = 480
        else:
            next_y = 440

        if self.current_level + 1 < len(LEVELS):
            next_name = LEVELS[self.current_level + 1]["name"]
            next_text = self.font_small.render(f"Next: {next_name}", True, LIGHT_GRAY)
            self.screen.blit(next_text, next_text.get_rect(center=(SCREEN_WIDTH // 2, next_y)))

        hint = self.font_small.render("Press Enter to continue", True, YELLOW)
        # Blink
        if self.state_timer % 60 < 40:
            self.screen.blit(hint, hint.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 80)))

    def _draw_game_over(self):
        # Dark background
        self.screen.fill((20, 10, 15))

        title = self.font_big.render("GAME OVER", True, RED)
        self.screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 200)))

        if self.game_over_reason:
            reason = self.font_med.render(self.game_over_reason, True, YELLOW)
            self.screen.blit(reason, reason.get_rect(center=(SCREEN_WIDTH // 2, 250)))

        score_text = self.font_med.render(f"Final Score: {self.total_score:06d}", True, WHITE)
        self.screen.blit(score_text, score_text.get_rect(center=(SCREEN_WIDTH // 2, 300)))

        if self.high_score > 0:
            hs_text = self.font_small.render(f"High Score: {self.high_score:06d}", True, GOLD)
            self.screen.blit(hs_text, hs_text.get_rect(center=(SCREEN_WIDTH // 2, 350)))

        hint = self.font_small.render("Enter: Retry   ESC: Main Menu", True, YELLOW)
        if self.state_timer % 60 < 40:
            self.screen.blit(hint, hint.get_rect(center=(SCREEN_WIDTH // 2, 450)))

    def _draw_victory(self):
        # Cached celebratory background
        cache_key = "victory_bg"
        if cache_key not in self._sky_cache:
            surf = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
            for i in range(SCREEN_HEIGHT):
                t = i / SCREEN_HEIGHT
                r = int(30 + (80 - 30) * t)
                g = int(20 + (60 - 20) * t)
                b = int(60 + (120 - 60) * t)
                pygame.draw.line(surf, (r, g, b), (0, i), (SCREEN_WIDTH, i))
            self._sky_cache[cache_key] = surf
        self.screen.blit(self._sky_cache[cache_key], (0, 0))

        # Confetti particles
        if self.state_timer % 5 == 0:
            x = random.randint(0, SCREEN_WIDTH)
            color = random.choice([RED, GREEN, BLUE, YELLOW, GOLD, PURPLE, PINK, ORANGE])
            self.particles.emit_burst(x, -10, color, count=3, speed=2, size=5, life=120, gravity=0.1)
        self.particles.update()
        self.particles.draw(self.screen, Camera(SCREEN_WIDTH, SCREEN_HEIGHT))

        title = self.font_big.render("VICTORY!", True, GOLD)
        shadow = self.font_big.render("VICTORY!", True, BLACK)
        self.screen.blit(shadow, shadow.get_rect(center=(SCREEN_WIDTH // 2 + 3, 163)))
        self.screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 160)))

        sub = self.font_med.render("You completed all levels!", True, WHITE)
        self.screen.blit(sub, sub.get_rect(center=(SCREEN_WIDTH // 2, 230)))

        score_text = self.font_med.render(f"Total Score: {self.total_score:06d}", True, YELLOW)
        self.screen.blit(score_text, score_text.get_rect(center=(SCREEN_WIDTH // 2, 310)))

        time_text = self.font_med.render(f"Total Time: {self.total_time:.1f}s", True, WHITE)
        self.screen.blit(time_text, time_text.get_rect(center=(SCREEN_WIDTH // 2, 360)))

        final = self._final_result or {}
        if final:
            diff_label = DIFFICULTY_CONFIG.get(
                final.get("difficulty", "normal"), DIFFICULTY_CONFIG["normal"]
            )["label"]
            medals = " ".join("*" if i < int(final.get("stars", 0)) else "-" for i in range(3))
            final_text = self.font_small.render(
                f"Final Stage ({diff_label}): {medals}   "
                f"Items {final.get('collected', 0)}/{final.get('total_items', 0)}   "
                f"Enemies {final.get('enemies_defeated', 0)}/{final.get('total_enemies', 0)}   "
                f"Deaths {final.get('deaths', 0)}",
                True, LIGHT_GRAY,
            )
            self.screen.blit(final_text, final_text.get_rect(center=(SCREEN_WIDTH // 2, 405)))
            achievements = final.get("achievements", [])
            if achievements:
                ach_names = ", ".join(a["name"] for a in achievements[:3])
                ach_text = self.font_small.render(f"New Achievements: {ach_names}", True, GOLD)
                self.screen.blit(ach_text, ach_text.get_rect(center=(SCREEN_WIDTH // 2, 438)))

        if self.new_high_score:
            new_record = self.font_med.render("NEW HIGH SCORE!", True, GOLD)
            if self.state_timer % 30 < 20:
                self.screen.blit(new_record, new_record.get_rect(center=(SCREEN_WIDTH // 2, 475)))

        hint = self.font_small.render("Press Enter to return to menu", True, LIGHT_GRAY)
        self.screen.blit(hint, hint.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 60)))

    def _draw_achievement_toasts(self):
        """Non-blocking achievement popups tucked into the upper-right HUD."""
        for i, toast in enumerate(self.achievement_toasts[:3]):
            record = toast["record"]
            timer = toast["timer"]
            alpha = min(230, timer * 4) if timer < 45 else 230
            box = pygame.Surface((310, 54), pygame.SRCALPHA)
            box.fill((20, 18, 32, alpha))
            pygame.draw.rect(box, (255, 200, 40, alpha), box.get_rect(), 2, border_radius=6)
            title = self.font_tiny.render("ACHIEVEMENT UNLOCKED", True, GOLD)
            name = self.font_small.render(record["name"], True, WHITE)
            box.blit(title, (12, 8))
            box.blit(name, (12, 26))
            self.screen.blit(box, (SCREEN_WIDTH - 330, 82 + i * 62))
