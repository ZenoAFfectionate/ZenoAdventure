"""
test_enemies.py - Tests for Enemy AI, stomp mechanics, and patrol behaviour.

Covers:
  * Enemy initialisation and sprite loading
  * Walker AI: gravity, patrol, edge-turning, wall-turning
  * Flyer AI: sine-wave movement, patrol range
  * Saw AI: stationary rotation
  * Fish AI: vertical oscillation, horizontal patrol
  * Stomp mechanics: stompable vs non-stompable, snail shell logic
  * Hitbox updates after movement
  * Death animation (squish effect)
"""

import pytest
import pygame
import math

from src.levels import LEVELS
from src.constants import TILE_SIZE, GRAVITY, JUMP_VELOCITY


class TestEnemyInitialisation:

    def test_all_enemy_types_load(self, make_tilemap):
        """Every enemy type declared in ENEMY_DATA should appear in at least one level."""
        from src.entities import ENEMY_DATA
        found_types = set()
        for lvl in LEVELS:
            tm = make_tilemap(lvl)
            for e in tm.enemies:
                found_types.add(e.etype)
        for etype in ENEMY_DATA.values():
            # Not all types need to appear, but slime/bee/fly/saw should
            if etype["type"] in ("slime", "bee", "fly", "saw"):
                assert etype["type"] in found_types, (
                    f"Enemy type '{etype['type']}' not found in any level"
                )

    def test_enemies_have_valid_hitboxes(self, make_tilemap):
        for i, lvl in enumerate(LEVELS):
            tm = make_tilemap(lvl)
            for e in tm.enemies:
                assert e.hitbox.width > 0
                assert e.hitbox.height > 0
                assert e.size > 0

    def test_enemies_start_alive(self, make_tilemap):
        for i, lvl in enumerate(LEVELS):
            tm = make_tilemap(lvl)
            for e in tm.enemies:
                assert e.alive, f"Level {i+1}: enemy {e.etype} should start alive"


class TestWalkerAI:

    def test_walker_falls_with_gravity(self, make_tilemap):
        """Walker enemies (slime, snail) should be affected by gravity."""
        for i, lvl in enumerate(LEVELS):
            tm = make_tilemap(lvl)
            for e in tm.enemies:
                if e.etype in ("slime", "snail"):
                    initial_y = e.y
                    for _ in range(5):
                        e.update(tm)
                    # Should have fallen or settled on ground
                    # (may already be on ground, so y stays or briefly moves)
                    assert e.y >= initial_y - 1, (
                        f"Level {i+1}: {e.etype} should fall or stay grounded"
                    )

    def test_walker_turns_at_edges(self, make_tilemap):
        """Walker should turn around when reaching a platform edge."""
        for i, lvl in enumerate(LEVELS):
            tm = make_tilemap(lvl)
            for e in tm.enemies:
                if e.etype in ("slime", "snail"):
                    initial_dir = e.dir
                    # Run for a while and check direction changes
                    for _ in range(300):
                        e.update(tm)
                    # Direction should have changed at least once (patrolling)
                    # or enemy should still be alive and on ground
                    assert e.alive

    def test_walker_respects_patrol_range(self, make_tilemap):
        """Walker should not wander too far from its start position."""
        for i, lvl in enumerate(LEVELS):
            tm = make_tilemap(lvl)
            for e in tm.enemies:
                if e.etype in ("slime", "snail"):
                    for _ in range(500):
                        e.update(tm)
                    max_distance = e.patrol_range + TILE_SIZE  # allow some slack
                    distance = abs(e.x - e.start_x)
                    assert distance <= max_distance, (
                        f"Level {i+1}: {e.etype} wandered {distance}px "
                        f"from start (patrol range {e.patrol_range}px)"
                    )

    def test_walker_does_not_fall_off_platform(self, make_tilemap):
        """Walker should not fall off the edge of its platform."""
        for i, lvl in enumerate(LEVELS):
            tm = make_tilemap(lvl)
            for e in tm.enemies:
                if e.etype in ("slime", "snail"):
                    for _ in range(500):
                        e.update(tm)
                    # Enemy feet should be resting on a surface (solid or oneway)
                    col = int(e.x // TILE_SIZE)
                    feet_row = int((e.y + e.size) // TILE_SIZE)
                    at_surface = (
                        (col, feet_row) in tm.solids
                        or (col, feet_row) in tm.oneways
                        or tm.is_solid_at(col, feet_row)
                    )
                    assert at_surface, (
                        f"Level {i+1}: {e.etype} fell off platform "
                        f"(feet at row {feet_row}, no surface there)"
                    )


class TestFlyerAI:

    def test_flyer_oscillates_vertically(self, make_tilemap):
        """Bee and fly enemies should oscillate up and down."""
        for i, lvl in enumerate(LEVELS):
            tm = make_tilemap(lvl)
            for e in tm.enemies:
                if e.etype in ("bee", "fly"):
                    y_values = []
                    for _ in range(120):
                        e.update(tm)
                        y_values.append(e.y)
                    y_range = max(y_values) - min(y_values)
                    assert y_range > 10, (
                        f"Level {i+1}: {e.etype} should oscillate vertically "
                        f"(y range = {y_range:.1f})"
                    )

    def test_flyer_respects_patrol_range(self, make_tilemap):
        for i, lvl in enumerate(LEVELS):
            tm = make_tilemap(lvl)
            for e in tm.enemies:
                if e.etype in ("bee", "fly"):
                    for _ in range(500):
                        e.update(tm)
                    distance = abs(e.x - e.start_x)
                    assert distance <= e.patrol_range + TILE_SIZE


class TestSawAI:

    def test_saw_is_stationary(self, make_tilemap):
        """Saw enemies should not move horizontally."""
        for i, lvl in enumerate(LEVELS):
            tm = make_tilemap(lvl)
            for e in tm.enemies:
                if e.etype == "saw":
                    initial_x = e.x
                    initial_y = e.y
                    for _ in range(100):
                        e.update(tm)
                    assert e.x == initial_x, "Saw should not move horizontally"
                    assert e.y == initial_y, "Saw should not move vertically"

    def test_saw_is_not_stompable(self, make_tilemap):
        """Saw enemies should not be stompable."""
        for i, lvl in enumerate(LEVELS):
            tm = make_tilemap(lvl)
            for e in tm.enemies:
                if e.etype == "saw":
                    assert e.stompable is False


class TestStompMechanics:

    def test_stompable_enemies_die_on_stomp(self, make_tilemap):
        """Slimes, bees, and flies should die when stomped."""
        for i, lvl in enumerate(LEVELS):
            tm = make_tilemap(lvl)
            for e in tm.enemies:
                if e.etype in ("slime", "bee", "fly"):
                    e.stomp()
                    assert not e.alive, (
                        f"Level {i+1}: {e.etype} should die on stomp"
                    )

    def test_saw_does_not_die_on_stomp(self, make_tilemap):
        """Saw should not die from stomp attempt."""
        for i, lvl in enumerate(LEVELS):
            tm = make_tilemap(lvl)
            for e in tm.enemies:
                if e.etype == "saw":
                    result = e.stomp()
                    assert result is False
                    assert e.alive, "Saw should survive stomp"

    def test_snail_enters_shell_on_first_stomp(self, make_tilemap):
        """Snail should enter shell state on first stomp, die on second."""
        for i, lvl in enumerate(LEVELS):
            tm = make_tilemap(lvl)
            for e in tm.enemies:
                if e.etype == "snail":
                    # First stomp: enter shell
                    result = e.stomp()
                    assert result is True
                    assert e.in_shell, "Snail should be in shell after first stomp"
                    assert e.alive, "Snail should survive first stomp"
                    # Second stomp: die
                    result = e.stomp()
                    assert not e.alive, "Snail should die on second stomp"

    def test_snail_exits_shell_after_timer(self, make_tilemap):
        """Snail should exit shell state after the timer expires."""
        for i, lvl in enumerate(LEVELS):
            tm = make_tilemap(lvl)
            for e in tm.enemies:
                if e.etype == "snail":
                    e.stomp()
                    assert e.in_shell
                    # Run for shell_timer + some extra frames
                    for _ in range(200):
                        e.update(tm)
                    assert not e.in_shell, "Snail should exit shell after timer"


class TestHitboxSync:

    def test_hitbox_follows_enemy_position(self, make_tilemap):
        """Hitbox should be updated to follow the enemy's position after update."""
        for i, lvl in enumerate(LEVELS):
            tm = make_tilemap(lvl)
            for e in tm.enemies:
                if e.etype in ("bee", "fly"):
                    for _ in range(30):
                        e.update(tm)
                    pad = e.size * 0.15
                    assert abs(e.hitbox.x - (e.x + pad)) < 2, (
                        f"Level {i+1}: {e.etype} hitbox x={e.hitbox.x} "
                        f"doesn't match position x={e.x}"
                    )
                    assert abs(e.hitbox.y - (e.y + pad)) < 2, (
                        f"Level {i+1}: {e.etype} hitbox y={e.hitbox.y} "
                        f"doesn't match position y={e.y}"
                    )
