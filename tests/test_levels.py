"""
test_levels.py - Level design validation tests.

Ensures every level is solvable and well-formed:
  * Key is placed before the lock (level is solvable)
  * All ground gaps are jumpable (width <= max jump distance)
  * All collectibles are reachable (within jump/spring range)
  * Springs are not buried underground
  * Checkpoints exist and are safe
  * Door is reachable after collecting the key
  * No springs placed below ground surface
"""

import pytest
import pygame

from src.levels import LEVELS
from src.constants import (
    TILE_SIZE, GRAVITY, JUMP_VELOCITY, PLAYER_MAX_SPEED,
    MAX_FALL_SPEED, SPRING_VELOCITY,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def walkable_surface_row(tm, col):
    """Return the topmost solid/oneway row at this column, or None."""
    for r in range(tm.height):
        if (col, r) in tm.solids or (col, r) in tm.oneways:
            return r
    return None


def max_jump_reach(height_diff_tiles, spring=False):
    """
    Simulate a full running jump arc and return (apex_tiles, landing_x_tiles).

    height_diff_tiles: target_row - start_row
      positive  → target is BELOW start (falling onto it)
      negative  → target is ABOVE start (jumping up to it)
      zero      → same height

    Returns (apex_above_start_in_tiles, horizontal_reach_in_tiles_at_landing)
    or (apex, None) if the trajectory never descends to target height.
    """
    vx = PLAYER_MAX_SPEED
    vy = SPRING_VELOCITY if spring else JUMP_VELOCITY
    x = 0.0
    y = 0.0
    target_y = height_diff_tiles * TILE_SIZE
    frames = 0
    min_y = 0.0
    landing_x = None
    while frames < 500:
        vx += (PLAYER_MAX_SPEED - vx) * 0.15
        vy += GRAVITY
        if vy > MAX_FALL_SPEED:
            vy = MAX_FALL_SPEED
        x += vx
        y += vy
        frames += 1
        min_y = min(min_y, y)
        if vy >= 0 and y >= target_y:
            landing_x = x / TILE_SIZE
            break
    apex = -min_y / TILE_SIZE
    return apex, landing_x


# ---------------------------------------------------------------------------
# Key-lock-door solvability
# ---------------------------------------------------------------------------
class TestKeyLockDoor:

    def test_key_exists_when_lock_exists(self, make_tilemap):
        """If a level has locks, it must also have a key."""
        for i, lvl in enumerate(LEVELS):
            tm = make_tilemap(lvl)
            if tm.locks:
                assert len(tm.key_positions) > 0, (
                    f"Level {i+1} has locks but no key — level is unsolvable"
                )

    def test_key_is_before_lock_horizontally(self, make_tilemap):
        """
        The key should be placed to the LEFT of the lock so the player
        encounters it first during left-to-right traversal.
        """
        for i, lvl in enumerate(LEVELS):
            tm = make_tilemap(lvl)
            if not tm.locks or not tm.key_positions:
                continue
            key_col = min(c for c, _ in tm.key_positions)
            lock_col = min(c for c, _ in tm.locks)
            assert key_col < lock_col, (
                f"Level {i+1}: key at col {key_col} is AFTER lock at col {lock_col} — "
                f"player encounters lock before key"
            )

    def test_lock_is_before_door(self, make_tilemap):
        """The lock should be between the key and the door."""
        for i, lvl in enumerate(LEVELS):
            tm = make_tilemap(lvl)
            if not tm.locks:
                continue
            lock_col = min(c for c, _ in tm.locks)
            door_col = tm.door_pos[0]
            assert lock_col < door_col, (
                f"Level {i+1}: lock at col {lock_col} is after door at col {door_col}"
            )

    def test_door_is_reachable_after_unlock(self, tmp_path):
        """
        Full playthrough via the shared harness (tests/simulate.py), which
        drives the real game loop: collect key → open locks → reach door.
        The door must be reachable without any impassable barrier.
        """
        from src.game import Game
        from tests.simulate import simulate_playthrough

        for i, lvl in enumerate(LEVELS):
            game = Game(progress_path=str(tmp_path / f"save_{i}.json"))
            result = simulate_playthrough(
                game, level_index=i, character="beige", max_frames=8000
            )
            assert result.reached, (
                f"Level {i+1} ({lvl['name']}): door not reached "
                f"(frames={result.frames}, final x={result.final_x:.1f}, "
                f"deaths={result.deaths}, game_over={result.game_over}) — "
                f"level may be unsolvable"
            )
            if lvl_has_locks(lvl):
                assert result.key_collected, (
                    f"Level {i+1}: door was reached without the key — "
                    f"lock gating is broken"
                )


def lvl_has_locks(lvl) -> bool:
    return any("k" in row for row in lvl["map"])


# ---------------------------------------------------------------------------
# Gap jumpability
# ---------------------------------------------------------------------------
class TestGapJumpability:

    def _get_walkable_segments(self, tm):
        """Return list of (row, col_start, col_end) for contiguous surfaces."""
        surf_by_col = {}
        for c in range(tm.width):
            best = None
            for r in range(tm.height):
                if (c, r) in tm.solids or (c, r) in tm.oneways:
                    best = r
                    break
            surf_by_col[c] = best
        segs = []
        cur_row = None
        start = None
        for c in range(tm.width):
            r = surf_by_col[c]
            if r != cur_row:
                if cur_row is not None:
                    segs.append((cur_row, start, c - 1))
                cur_row = r
                start = c
        if cur_row is not None:
            segs.append((cur_row, start, tm.width - 1))
        return [s for s in segs if s[0] is not None]

    def test_all_gaps_are_jumpable(self, make_tilemap):
        """
        Every horizontal gap between walkable surfaces must be crossable
        with a normal or spring-assisted jump.
        """
        for i, lvl in enumerate(LEVELS):
            tm = make_tilemap(lvl)
            segs = self._get_walkable_segments(tm)
            for j in range(len(segs) - 1):
                row_a, sa, ea = segs[j]
                row_b, sb, eb = segs[j + 1]
                gap = sb - ea - 1
                if gap <= 0:
                    continue
                height_diff = row_b - row_a
                apex, landing_x = max_jump_reach(height_diff)
                needed_height = max(0, -height_diff)
                height_ok = apex >= needed_height
                reach_ok = landing_x is not None and landing_x >= gap
                assert height_ok and reach_ok, (
                    f"Level {i+1}: gap cols[{ea+1},{sb-1}] width={gap} "
                    f"height_diff={height_diff} — not jumpable "
                    f"(apex={apex:.2f} needed={needed_height}, reach={landing_x})"
                )


# ---------------------------------------------------------------------------
# Collectible reachability
# ---------------------------------------------------------------------------
class TestCollectibleReachability:

    def test_collectibles_near_surface(self, make_tilemap):
        """
        Every collectible should be within ~5 tiles vertically of the
        nearest walkable surface (reachable by jump or spring).
        """
        for i, lvl in enumerate(LEVELS):
            tm = make_tilemap(lvl)
            for item in tm.collectibles:
                # Find nearest surface in adjacent columns
                best_dist = None
                for dc in range(-3, 4):
                    c = item.col + dc
                    if c < 0 or c >= tm.width:
                        continue
                    sr = walkable_surface_row(tm, c)
                    if sr is not None:
                        dist = abs(sr - 1 - item.row)  # sr-1 = walking level
                        if best_dist is None or dist < best_dist:
                            best_dist = dist
                # Allow up to 7 tiles (spring bounce reaches ~6.7 tiles)
                assert best_dist is not None and best_dist <= 7, (
                    f"Level {i+1}: collectible '{item.kind}' at "
                    f"({item.col},{item.row}) is {best_dist} tiles from "
                    f"nearest surface — likely unreachable"
                )

    def test_high_collectibles_have_nearby_spring(self, make_tilemap):
        """
        Collectibles more than 3 tiles above the nearest surface
        require a spring to reach.  Ensure a spring exists nearby.
        """
        for i, lvl in enumerate(LEVELS):
            tm = make_tilemap(lvl)
            for item in tm.collectibles:
                best_dist = None
                for dc in range(-3, 4):
                    c = item.col + dc
                    if c < 0 or c >= tm.width:
                        continue
                    sr = walkable_surface_row(tm, c)
                    if sr is not None:
                        dist = abs(sr - 1 - item.row)
                        if best_dist is None or dist < best_dist:
                            best_dist = dist
                if best_dist is not None and best_dist > 3:
                    # Need a spring within a few tiles
                    spring_nearby = any(
                        abs(sc - item.col) <= 3 for (sc, _) in tm.springs
                    )
                    assert spring_nearby, (
                        f"Level {i+1}: collectible '{item.kind}' at "
                        f"({item.col},{item.row}) is {best_dist} tiles high "
                        f"but no spring within 3 tiles — unreachable"
                    )


# ---------------------------------------------------------------------------
# Spring placement
# ---------------------------------------------------------------------------
class TestSpringPlacement:

    def test_springs_are_on_ground_surface(self, make_tilemap):
        """
        Springs should not be buried underground (solid tile above them).
        Springs are solid tiles themselves and can bridge gaps/hazards.
        """
        for i, lvl in enumerate(LEVELS):
            tm = make_tilemap(lvl)
            for (c, r) in tm.springs:
                # Spring should not have a solid tile directly above it
                above_solid = (c, r - 1) in tm.solids
                assert not above_solid, (
                    f"Level {i+1}: spring at ({c},{r}) is buried under a solid tile"
                )

    def test_springs_not_buried(self, make_tilemap):
        """A spring should not have a solid tile directly above it."""
        for i, lvl in enumerate(LEVELS):
            tm = make_tilemap(lvl)
            for (c, r) in tm.springs:
                above_solid = (c, r - 1) in tm.solids
                assert not above_solid, (
                    f"Level {i+1}: spring at ({c},{r}) is buried under a solid tile"
                )


# ---------------------------------------------------------------------------
# No "box on ground" — solid blocks that look like misplaced crates
# ---------------------------------------------------------------------------
class TestNoBoxesOnGround:
    """
    Solid '=' blocks at the walking level that sit directly on top of
    ground look like misplaced crates/boxes.  Either:
      * They are removed (no purpose)
      * Or they form a clear platform (extend across a gap, or are tall
        enough to be an intentional raised area)
    """

    def test_solid_blocks_serve_a_purpose(self, make_tilemap):
        """
        A walking-level solid block must either:
          1. Be part of a continuous ground segment (row 8 or 9, spanning
             many columns), or
          2. Span across a gap (so it serves as a platform over the gap)
        """
        for i, lvl in enumerate(LEVELS):
            tm = make_tilemap(lvl)
            for (c, r) in sorted(tm.solids):
                ch = tm._char_at(c, r)
                if ch != '=':
                    continue
                # Only check walking-level blocks (row 7 or 8)
                if r not in (7, 8):
                    continue
                # Check if directly above ground
                if (c, r + 1) not in tm.solids:
                    continue
                # This block sits on ground.  Check if it's a platform over a gap:
                # the tile below the ground (r+2) should be empty
                is_over_gap = (c, r + 2) not in tm.solids
                assert is_over_gap, (
                    f"Level {i+1}: '=' block at ({c},{r}) sits on continuous ground "
                    f"and looks like a misplaced box.  Use '---' for platforms or "
                    f"extend the ground instead."
                )


# ---------------------------------------------------------------------------
# Checkpoint coverage
# ---------------------------------------------------------------------------
class TestCheckpointCoverage:

    def test_each_level_has_at_least_one_checkpoint(self, make_tilemap):
        """
        Every level should have at least one checkpoint flag to prevent
        excessive backtracking on death.

        BUG: Only Level 1 has a checkpoint; Levels 2-5 have none.
        """
        for i, lvl in enumerate(LEVELS):
            tm = make_tilemap(lvl)
            assert len(tm.flag_positions) > 0, (
                f"Level {i+1} ({lvl['name']}) has no checkpoint flags — "
                f"falling in a pit sends the player all the way back to start"
            )
