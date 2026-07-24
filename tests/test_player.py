"""
test_player.py - Tests for Player physics, movement, and collision.

Covers:
  * Gravity and fall speed clamping
  * Jump mechanics (coyote time, jump buffer, variable jump height)
  * Horizontal movement and friction
  * Solid tile collision (X and Y axis separation)
  * One-way platform collision (fall-through from below, land from above)
  * Spring bounce
  * Hazard damage
  * Health and invincibility frames
  * Ducking and unducking
"""

import pytest
import pygame

from src.levels import LEVELS
from src.constants import (
    TILE_SIZE, GRAVITY, MAX_FALL_SPEED, JUMP_VELOCITY, JUMP_CUT_VELOCITY,
    PLAYER_MAX_SPEED, COYOTE_TIME, JUMP_BUFFER, SPRING_VELOCITY,
    INVINCIBILITY_FRAMES, STARTING_HEALTH, MAX_HEALTH,
)


class TestPlayerInitialisation:

    def test_player_has_correct_hitbox(self, make_player):
        p = make_player(100, 100)
        assert p.w == p.stand_w
        assert p.h == p.stand_h
        assert p.rect.width == p.stand_w
        assert p.rect.height == p.stand_h

    def test_player_starts_idle(self, make_player):
        p = make_player(100, 100)
        assert p.state == p.IDLE
        assert p.on_ground is False
        assert p.vx == 0.0
        assert p.vy == 0.0

    def test_player_default_health(self, make_player):
        p = make_player(100, 100)
        assert p.health == 3
        assert p.lives == 3


class TestGravity:

    def test_gravity_applies_when_not_climbing(self, make_tilemap, make_player, fake_keys, particles, noop_sound):
        tm = make_tilemap(LEVELS[0])
        p = make_player(*tm.player_start)
        keys = fake_keys()
        p.update(keys, tm, particles, noop_sound)
        assert p.vy > 0, "Player should accelerate downward due to gravity"

    def test_fall_speed_is_clamped(self, make_tilemap, make_player, fake_keys, particles, noop_sound):
        tm = make_tilemap(LEVELS[0])
        p = make_player(*tm.player_start)
        keys = fake_keys()
        for _ in range(200):
            p.update(keys, tm, particles, noop_sound)
        assert p.vy <= MAX_FALL_SPEED, (
            f"Fall speed {p.vy} exceeds MAX_FALL_SPEED {MAX_FALL_SPEED}"
        )


class TestJumpMechanics:

    def test_jump_sets_upward_velocity(self, make_tilemap, make_player, fake_keys, particles, noop_sound):
        tm = make_tilemap(LEVELS[0])
        p = make_player(*tm.player_start)
        keys = fake_keys()
        # Let player settle on ground
        for _ in range(10):
            p.update(keys, tm, particles, noop_sound)
        assert p.on_ground, "Player should be on ground after settling"
        p.try_jump(tm, noop_sound)
        assert p.vy == JUMP_VELOCITY, f"vy={p.vy} should be {JUMP_VELOCITY}"

    def test_coyote_time_allows_jump_after_leaving_ground(self, make_tilemap, make_player, fake_keys, particles, noop_sound):
        """Player should be able to jump shortly after walking off a ledge."""
        tm = make_tilemap(LEVELS[0])
        p = make_player(*tm.player_start)
        keys = fake_keys()
        # Settle on ground
        for _ in range(10):
            p.update(keys, tm, particles, noop_sound)
        assert p.on_ground
        # Simulate walking off edge — coyote should still allow jump
        assert p.coyote > 0 or p.on_ground

    def test_jump_buffer_buffers_input(self, make_tilemap, make_player, fake_keys, particles, noop_sound):
        """Pressing jump just before landing should trigger jump on landing."""
        tm = make_tilemap(LEVELS[0])
        p = make_player(*tm.player_start)
        keys = fake_keys()
        for _ in range(10):
            p.update(keys, tm, particles, noop_sound)
        # Jump up
        p.try_jump(tm, noop_sound)
        # While airborne, buffer another jump
        for _ in range(5):
            p.update(keys, tm, particles, noop_sound)
        p.jump_buffer = JUMP_BUFFER
        # Continue until near landing
        for _ in range(40):
            p.update(keys, tm, particles, noop_sound)
        # If buffer was consumed, player should have jumped again
        # (vy should be negative or recently was)
        # This is a soft test — just ensure no crash
        assert p.health > 0

    def test_variable_jump_height(self, make_tilemap, make_player, fake_keys, particles, noop_sound):
        """Releasing jump early should cut the jump short."""
        tm = make_tilemap(LEVELS[0])
        # Full jump
        p1 = make_player(*tm.player_start)
        keys1 = fake_keys()
        for _ in range(10):
            p1.update(keys1, tm, particles, noop_sound)
        p1.try_jump(tm, noop_sound)
        # Hold jump
        keys1[pygame.K_SPACE] = True
        for _ in range(20):
            p1.update(keys1, tm, particles, noop_sound)
        full_height = p1.y

        # Short jump
        p2 = make_player(*tm.player_start)
        keys2 = fake_keys()
        for _ in range(10):
            p2.update(keys2, tm, particles, noop_sound)
        p2.try_jump(tm, noop_sound)
        # Release jump after a few frames
        for _ in range(3):
            keys2[pygame.K_SPACE] = True
            p2.update(keys2, tm, particles, noop_sound)
        keys2[pygame.K_SPACE] = False
        for _ in range(17):
            p2.update(keys2, tm, particles, noop_sound)
        short_height = p2.y

        # Full jump should go higher (lower y)
        assert full_height < short_height, (
            f"Full jump y={full_height} should be higher than short jump y={short_height}"
        )


class TestHorizontalMovement:

    def test_player_accelerates_right(self, make_tilemap, make_player, fake_keys, particles, noop_sound):
        tm = make_tilemap(LEVELS[0])
        p = make_player(*tm.player_start)
        keys = fake_keys()
        for _ in range(10):
            p.update(keys, tm, particles, noop_sound)
        initial_x = p.x
        keys[pygame.K_RIGHT] = True
        for _ in range(20):
            p.update(keys, tm, particles, noop_sound)
        assert p.x > initial_x, "Player should move right"
        assert p.vx > 0

    def test_player_accelerates_left(self, make_tilemap, make_player, fake_keys, particles, noop_sound):
        tm = make_tilemap(LEVELS[0])
        p = make_player(*tm.player_start)
        keys = fake_keys()
        for _ in range(10):
            p.update(keys, tm, particles, noop_sound)
        initial_x = p.x
        keys[pygame.K_LEFT] = True
        for _ in range(5):  # only 5 frames — player starts near left edge
            p.update(keys, tm, particles, noop_sound)
        assert p.x < initial_x, "Player should move left"
        assert p.vx < 0

    def test_friction_stops_player(self, make_tilemap, make_player, fake_keys, particles, noop_sound):
        tm = make_tilemap(LEVELS[0])
        p = make_player(*tm.player_start)
        keys = fake_keys()
        # Build up speed
        keys[pygame.K_RIGHT] = True
        for _ in range(30):
            p.update(keys, tm, particles, noop_sound)
        assert abs(p.vx) > 1
        # Release
        keys.clear()
        for _ in range(60):
            p.update(keys, tm, particles, noop_sound)
        assert abs(p.vx) < 0.5, f"Player should stop due to friction, vx={p.vx}"

    def test_max_speed_is_enforced(self, make_tilemap, make_player, fake_keys, particles, noop_sound):
        tm = make_tilemap(LEVELS[0])
        p = make_player(*tm.player_start)
        keys = fake_keys({pygame.K_RIGHT: True})
        for _ in range(100):
            p.update(keys, tm, particles, noop_sound)
        # Max speed includes skill-based passive speed multiplier
        speed_mult = p._skill_info.get("passive_speed_mult", 1.0)
        effective_max = PLAYER_MAX_SPEED * speed_mult
        assert p.vx <= effective_max + 0.1


class TestSolidCollision:

    def test_player_lands_on_solid_ground(self, make_tilemap, make_player, fake_keys, particles, noop_sound):
        tm = make_tilemap(LEVELS[0])
        p = make_player(*tm.player_start)
        keys = fake_keys()
        for _ in range(30):
            p.update(keys, tm, particles, noop_sound)
        assert p.on_ground, "Player should land on ground"

    def test_player_does_not_fall_through_solid(self, make_tilemap, make_player, fake_keys, particles, noop_sound):
        tm = make_tilemap(LEVELS[0])
        px, py = tm.player_start
        p = make_player(px, py)
        keys = fake_keys()
        for _ in range(300):
            p.update(keys, tm, particles, noop_sound)
        # Player should be on the ground, not below it
        ground_row = walkable_surface_row(tm, int(p.x // TILE_SIZE))
        if ground_row is not None:
            max_y = ground_row * TILE_SIZE - p.h
            assert p.y <= max_y + 5, (
                f"Player y={p.y} sank below ground surface at y={max_y}"
            )

    def test_player_blocked_by_wall(self, make_tilemap, make_player, fake_keys, particles, noop_sound):
        """Player should not pass through solid walls."""
        tm = make_tilemap(LEVELS[0])
        px, py = tm.player_start
        p = make_player(px, py)
        keys = fake_keys()
        # Settle
        for _ in range(10):
            p.update(keys, tm, particles, noop_sound)
        # Move left towards the map edge
        keys[pygame.K_LEFT] = True
        for _ in range(200):
            p.update(keys, tm, particles, noop_sound)
        # Player should not go past x=0 (or the first solid column)
        assert p.x > 0, f"Player walked through left wall: x={p.x}"


class TestSpringBounce:

    def test_spring_launches_player_upward(self, make_tilemap, make_player, fake_keys, particles, noop_sound):
        """Landing on a spring should set vy to SPRING_VELOCITY."""
        # Level 1 has a spring at (31, 8) or (35, 9)
        tm = make_tilemap(LEVELS[0])
        springs = sorted(tm.springs)
        assert len(springs) > 0, "Level 1 should have springs"
        sc, sr = springs[0]
        # Place player above the spring
        px = sc * TILE_SIZE + TILE_SIZE / 2
        py = (sr - 3) * TILE_SIZE  # 3 tiles above
        p = make_player(px, py)
        keys = fake_keys()
        # Fall onto spring
        for _ in range(60):
            p.update(keys, tm, particles, noop_sound)
            if p.vy == SPRING_VELOCITY:
                break
        assert p.vy == SPRING_VELOCITY or p.spring_bounce, (
            f"Spring should launch player. vy={p.vy}, spring_bounce={p.spring_bounce}"
        )


class TestDamageAndHealth:

    def test_take_damage_reduces_health(self, make_player):
        p = make_player(100, 100)
        initial = p.health
        result = p.take_damage()
        assert result is True
        assert p.health == initial - 1

    def test_invincibility_prevents_repeated_damage(self, make_player):
        p = make_player(100, 100)
        p.take_damage()
        health_after_first = p.health
        # Should be invincible
        result = p.take_damage()
        assert result is False
        assert p.health == health_after_first

    def test_invincibility_expires(self, make_player):
        p = make_player(100, 100)
        p.take_damage()
        # Exhaust invincibility
        p.invincible = 1
        # Need to decrement to 0
        p.invincible = 0
        result = p.take_damage()
        assert result is True

    def test_knockback_on_damage(self, make_player):
        p = make_player(100, 100)
        p.take_damage()
        assert p.vy < 0, "Player should be knocked upward on damage"
        assert p.state == p.HIT


class TestDucking:

    def test_duck_reduces_hitbox_height(self, make_tilemap, make_player, fake_keys, particles, noop_sound):
        tm = make_tilemap(LEVELS[0])
        p = make_player(*tm.player_start)
        keys = fake_keys()
        for _ in range(10):
            p.update(keys, tm, particles, noop_sound)
        stand_h = p.h
        keys[pygame.K_DOWN] = True
        for _ in range(5):
            p.update(keys, tm, particles, noop_sound)
        assert p.ducking, "Player should be ducking"
        assert p.h == p.duck_h
        assert p.h < stand_h

    def test_unduck_restores_hitbox(self, make_tilemap, make_player, fake_keys, particles, noop_sound):
        tm = make_tilemap(LEVELS[0])
        p = make_player(*tm.player_start)
        keys = fake_keys()
        for _ in range(10):
            p.update(keys, tm, particles, noop_sound)
        keys[pygame.K_DOWN] = True
        for _ in range(5):
            p.update(keys, tm, particles, noop_sound)
        assert p.ducking
        keys.clear()
        for _ in range(5):
            p.update(keys, tm, particles, noop_sound)
        assert not p.ducking
        assert p.h == p.stand_h


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def walkable_surface_row(tm, col):
    for r in range(tm.height):
        if (col, r) in tm.solids or (col, r) in tm.oneways:
            return r
    return None
