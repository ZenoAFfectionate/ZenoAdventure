"""
test_tilemap.py - Tests for TileMap parsing, collision detection, and boundary handling.

Covers:
  * ASCII map parsing correctness (solids, oneways, springs, hazards, etc.)
  * _snap_row_to_ground behaviour
  * is_solid_at boundary logic (invisible side walls)
  * rect_collides_solid / rect_collides_hazard / rect_collides_water
  * Key/lock/door/flag parsing and snapping
  * Spring tile solidity
  * Ground-below detection for walker enemy edge-turning
"""

import pytest
import pygame

from src.levels import LEVELS
from src.constants import TILE_SIZE


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
class TestTileMapParsing:

    def test_all_levels_parse_without_error(self, make_tilemap):
        """Every level in LEVELS should parse cleanly."""
        for i, lvl in enumerate(LEVELS):
            tm = make_tilemap(lvl)
            assert tm.width > 0
            assert tm.height > 0
            assert tm.pixel_w == tm.width * TILE_SIZE
            assert tm.pixel_h == tm.height * TILE_SIZE

    def test_player_start_is_set(self, make_tilemap):
        """Every level must have a valid player start position."""
        for i, lvl in enumerate(LEVELS):
            tm = make_tilemap(lvl)
            assert tm.player_start != (0, 0), f"Level {i+1} has no player start"
            px, py = tm.player_start
            assert 0 <= px < tm.pixel_w
            assert 0 <= py < tm.pixel_h

    def test_door_pos_is_set(self, make_tilemap):
        """Every level must have a door position."""
        for i, lvl in enumerate(LEVELS):
            tm = make_tilemap(lvl)
            assert tm.door_pos is not None, f"Level {i+1} has no door"

    def test_solid_tiles_include_springs(self, make_tilemap):
        """Springs should be in both self.springs and self.solids."""
        for i, lvl in enumerate(LEVELS):
            tm = make_tilemap(lvl)
            for (c, r) in tm.springs:
                assert (c, r) in tm.solids, (
                    f"Level {i+1}: spring at ({c},{r}) is not in solids set"
                )

    def test_map_rows_are_padded(self, make_tilemap):
        """All rows should be padded to the map width."""
        for i, lvl in enumerate(LEVELS):
            tm = make_tilemap(lvl)
            for row in tm.raw_map:
                # ljust is applied during parse; raw may differ but width is max
                assert len(row) <= tm.width


# ---------------------------------------------------------------------------
# Boundary collision — THE CRITICAL BUG
# ---------------------------------------------------------------------------
class TestBoundaryCollision:
    """
    is_solid_at() declares invisible side walls (col < 0 and col >= width
    return True).  However, the rect-based collision helpers clamp
    col1 = min(width-1, rect.right // TILE_SIZE), which means they NEVER
    check the out-of-bounds column.  This allows the player to walk or
    fall off the left/right edges of the map.

    These tests document the expected behaviour so that any fix can be
    validated against them.
    """

    def test_is_solid_at_left_edge(self, make_tilemap):
        """Column -1 should be treated as solid (invisible left wall)."""
        tm = make_tilemap(LEVELS[0])
        assert tm.is_solid_at(-1, 5) is True

    def test_is_solid_at_right_edge(self, make_tilemap):
        """Column == width should be treated as solid (invisible right wall)."""
        tm = make_tilemap(LEVELS[0])
        assert tm.is_solid_at(tm.width, 5) is True

    def test_is_solid_at_top_open(self, make_tilemap):
        """Row -1 (above map) should NOT be solid — top is open."""
        tm = make_tilemap(LEVELS[0])
        assert tm.is_solid_at(5, -1) is False

    def test_is_solid_at_bottom_open(self, make_tilemap):
        """Row == height (below map) should NOT be solid — bottom is open."""
        tm = make_tilemap(LEVELS[0])
        assert tm.is_solid_at(5, tm.height) is False

    def test_rect_past_right_edge_is_detected_as_solid(self, make_tilemap):
        """
        A rect that extends past the right edge of the map MUST be
        reported as colliding with a solid (the invisible wall).

        BUG: rect_collides_solid clamps col1 to width-1 and never
        checks column `width`, so it returns False even though
        is_solid_at(width, row) is True.
        """
        tm = make_tilemap(LEVELS[0])
        # Place a rect straddling the right boundary
        rect = pygame.Rect(
            tm.pixel_w - 10,          # left: 10px before edge
            8 * TILE_SIZE,             # top: mid-map
            40,                        # width: extends 30px past edge
            TILE_SIZE,
        )
        assert tm.is_solid_at(tm.width, 8) is True  # invisible wall exists
        assert tm.rect_collides_solid(rect) is True, (
            "Player rect extending past right edge is not blocked — "
            "rect_collides_solid fails to check out-of-bounds columns"
        )

    def test_rect_past_left_edge_is_detected_as_solid(self, make_tilemap):
        """Same issue for the left edge."""
        tm = make_tilemap(LEVELS[0])
        rect = pygame.Rect(
            -30,                       # left: 30px past left edge
            8 * TILE_SIZE,
            40,
            TILE_SIZE,
        )
        assert tm.is_solid_at(-1, 8) is True
        assert tm.rect_collides_solid(rect) is True, (
            "Player rect extending past left edge is not blocked"
        )

    def test_player_cannot_walk_off_right_edge(self, make_tilemap, make_player, fake_keys, particles, noop_sound):
        """
        End-to-end test: running right continuously should NOT let the
        player escape past the map's right boundary.

        BUG: Due to the clamping bug, the player can walk off the right
        edge and fall into the void.
        """
        tm = make_tilemap(LEVELS[0])
        px, py = tm.player_start
        player = make_player(px, py)
        keys = fake_keys({pygame.K_RIGHT: True})

        for _ in range(3000):
            player.update(keys, tm, particles, noop_sound)
            # Player should never exceed the map's pixel width
            assert player.x < tm.pixel_w, (
                f"Player escaped right edge: x={player.x} > pixel_w={tm.pixel_w}"
            )

    def test_player_cannot_walk_off_left_edge(self, make_tilemap, make_player, fake_keys, particles, noop_sound):
        """Same for the left edge."""
        tm = make_tilemap(LEVELS[0])
        px, py = tm.player_start
        player = make_player(px, py)
        keys = fake_keys({pygame.K_LEFT: True})

        for _ in range(3000):
            player.update(keys, tm, particles, noop_sound)
            assert player.x > 0, (
                f"Player escaped left edge: x={player.x}"
            )


# ---------------------------------------------------------------------------
# Ground snapping
# ---------------------------------------------------------------------------
class TestSnapToGround:

    def test_keys_are_snapped_to_ground(self, make_tilemap):
        """Keys should be snapped so there's ground directly below them."""
        for i, lvl in enumerate(LEVELS):
            tm = make_tilemap(lvl)
            for (c, r) in tm.key_positions:
                below = (c, r + 1)
                has_ground = (
                    (c, r + 1) in tm.solids
                    or (c, r + 1) in tm.oneways
                    or tm.is_solid_at(c, r + 1)
                )
                assert has_ground, (
                    f"Level {i+1}: key at ({c},{r}) has no ground below at ({c},{r+1})"
                )

    def test_locks_are_snapped_to_ground(self, make_tilemap):
        """Locks should have ground directly below."""
        for i, lvl in enumerate(LEVELS):
            tm = make_tilemap(lvl)
            for (c, r) in tm.locks:
                has_ground = (
                    (c, r + 1) in tm.solids
                    or (c, r + 1) in tm.oneways
                    or tm.is_solid_at(c, r + 1)
                )
                assert has_ground, (
                    f"Level {i+1}: lock at ({c},{r}) has no ground below"
                )

    def test_door_is_snapped_to_ground(self, make_tilemap):
        """Door should have ground directly below."""
        for i, lvl in enumerate(LEVELS):
            tm = make_tilemap(lvl)
            dc, dr = tm.door_pos
            has_ground = (
                (dc, dr + 1) in tm.solids
                or (dc, dr + 1) in tm.oneways
                or tm.is_solid_at(dc, dr + 1)
            )
            assert has_ground, (
                f"Level {i+1}: door at ({dc},{dr}) has no ground below"
            )

    def test_walker_enemies_are_on_ground(self, make_tilemap):
        """Slime and snail enemies should start standing on ground."""
        for i, lvl in enumerate(LEVELS):
            tm = make_tilemap(lvl)
            for enemy in tm.enemies:
                if enemy.etype in ("slime", "snail"):
                    col = int(enemy.x // TILE_SIZE)
                    row = int((enemy.y + enemy.size) // TILE_SIZE)
                    has_ground = (
                        (col, row) in tm.solids
                        or (col, row) in tm.oneways
                        or tm.is_solid_at(col, row)
                    )
                    assert has_ground, (
                        f"Level {i+1}: {enemy.etype} at col={col} "
                        f"is not standing on ground (row {row})"
                    )


# ---------------------------------------------------------------------------
# Checkpoint safety
# ---------------------------------------------------------------------------
class TestCheckpointSafety:

    def test_checkpoints_have_ground_below(self, make_tilemap):
        """
        Every checkpoint (flag) position must have solid ground directly
        below it.  If a checkpoint is over a pit, respawning there causes
        an immediate fall-death loop.

        BUG: Level 1's flag at (23, 7) sits over a 3-tile-wide pit
        (cols 22-24 have no ground at any row).
        """
        for i, lvl in enumerate(LEVELS):
            tm = make_tilemap(lvl)
            for (c, r) in tm.flag_positions:
                has_ground = (
                    (c, r + 1) in tm.solids
                    or (c, r + 1) in tm.oneways
                    or tm.is_solid_at(c, r + 1)
                )
                assert has_ground, (
                    f"Level {i+1}: checkpoint at ({c},{r}) is over a pit — "
                    f"respawning here causes fall-death loop"
                )

    def test_respawn_at_checkpoint_does_not_fall(self, make_tilemap, make_player, fake_keys, particles, noop_sound):
        """
        Placing the player at each checkpoint and applying gravity should
        result in landing on ground, not falling out of the map.
        """
        for i, lvl in enumerate(LEVELS):
            tm = make_tilemap(lvl)
            for (c, r) in tm.flag_positions:
                px = c * TILE_SIZE
                py = r * TILE_SIZE
                player = make_player(px, py)
                keys = fake_keys()  # no input
                fell_out = False
                for _ in range(200):
                    player.update(keys, tm, particles, noop_sound)
                    if player.y > tm.pixel_h + 100:
                        fell_out = True
                        break
                assert not fell_out, (
                    f"Level {i+1}: player falls out of map when respawning "
                    f"at checkpoint ({c},{r})"
                )


# ---------------------------------------------------------------------------
# Hazard collision
# ---------------------------------------------------------------------------
class TestHazardCollision:

    def test_rect_collides_hazard_detects_spikes(self, make_tilemap):
        """A rect overlapping a spike tile should be detected."""
        tm = make_tilemap(LEVELS[0])
        # Find a hazard tile if any level has one
        if tm.hazards:
            (hc, hr) = next(iter(tm.hazards))
            rect = pygame.Rect(hc * TILE_SIZE, hr * TILE_SIZE, TILE_SIZE, TILE_SIZE)
            assert tm.rect_collides_hazard(rect) is True

    def test_rect_collides_hazard_returns_false_for_empty(self, make_tilemap):
        """A rect in empty space should not collide with hazards."""
        tm = make_tilemap(LEVELS[0])
        # Use a position high above the map content
        rect = pygame.Rect(0, 0, TILE_SIZE, TILE_SIZE)
        assert tm.rect_collides_hazard(rect) is False


# ---------------------------------------------------------------------------
# Ground-below detection (used by walker enemy edge-turning)
# ---------------------------------------------------------------------------
class TestHasGroundBelow:

    def test_returns_true_when_ground_exists(self, make_tilemap):
        tm = make_tilemap(LEVELS[0])
        # Col 0, row 8 should have ground at row 9
        assert tm.has_ground_below(0, 8, max_depth=3) is True

    def test_returns_false_when_no_ground(self, make_tilemap):
        tm = make_tilemap(LEVELS[0])
        # Use a column known to be a gap at ground level
        # Level 1 gap is at cols 8-10 (row 9)
        assert tm.has_ground_below(9, 8, max_depth=2) is False
