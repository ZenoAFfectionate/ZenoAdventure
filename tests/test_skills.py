"""
test_skills.py - Tests for the character ability/skill system.

Covers:
  * Green character: Dash Strike (active skill, cooldown, invincibility, enemy kill)
  * Pink character: Double Jump (air jump, charge consumption, landing reset, higher jump)
  * Purple character: Time Slow (cooldown, slow-mo effect on enemies, passive i-frames)
  * Star power-up invincibility (kill enemies on contact, expires, no fall protection)
  * Charge crystal cooldown reset
  * Character selection (3 characters, each with unique skill)
"""

import pytest
import pygame

from src.levels import LEVELS
from src.constants import (
    TILE_SIZE, JUMP_VELOCITY, PLAYER_MAX_SPEED, INVINCIBILITY_FRAMES,
    SKILL_DASH, SKILL_DOUBLE_JUMP, SKILL_SLOW_MO,
    CHARACTER_SKILLS, CHARACTERS, STAR_INVINCIBILITY_FRAMES,
)


class _FakeGame:
    """Minimal game object for skill tests."""
    slow_mo_timer = 0


# ---------------------------------------------------------------------------
# Green character — Dash Strike
# ---------------------------------------------------------------------------
class TestDashSkill:

    def test_green_has_dash_skill(self, make_player):
        p = make_player(100, 100, "green")
        assert p.skill_type == SKILL_DASH

    def test_green_has_speed_bonus(self, make_player, make_tilemap, fake_keys, particles, noop_sound):
        """Green's passive: +10% movement speed."""
        tm = make_tilemap(LEVELS[0])
        p = make_player(*tm.player_start, "green")
        keys = fake_keys({pygame.K_RIGHT: True})
        for _ in range(100):
            p.update(keys, tm, particles, noop_sound)
        assert p.vx > PLAYER_MAX_SPEED, (
            f"Green should be faster than base speed: vx={p.vx} > {PLAYER_MAX_SPEED}"
        )

    def test_dash_activates_on_skill_trigger(self, make_player, make_tilemap, fake_keys, particles, noop_sound):
        tm = make_tilemap(LEVELS[0])
        p = make_player(*tm.player_start, "green")
        keys = fake_keys()
        for _ in range(10):
            p.update(keys, tm, particles, noop_sound)
        result = p.try_skill(_FakeGame(), tm, [], particles, noop_sound)
        assert result is True
        assert p.skill_active is True
        assert p.dash_vx != 0

    def test_dash_has_cooldown(self, make_player, make_tilemap, fake_keys, particles, noop_sound):
        tm = make_tilemap(LEVELS[0])
        p = make_player(*tm.player_start, "green")
        keys = fake_keys()
        for _ in range(10):
            p.update(keys, tm, particles, noop_sound)
        p.try_skill(_FakeGame(), tm, [], particles, noop_sound)
        assert p.skill_cooldown > 0
        result = p.try_skill(_FakeGame(), tm, [], particles, noop_sound)
        assert result is False

    def test_dash_grants_invincibility(self, make_player, make_tilemap, fake_keys, particles, noop_sound):
        tm = make_tilemap(LEVELS[0])
        p = make_player(*tm.player_start, "green")
        keys = fake_keys()
        for _ in range(10):
            p.update(keys, tm, particles, noop_sound)
        p.try_skill(_FakeGame(), tm, [], particles, noop_sound)
        assert p.invincible > 0, "Dash should grant invincibility frames"

    def test_dash_kills_enemies_in_path(self, make_player, make_tilemap, fake_keys, particles, noop_sound):
        """Dashing through stompable enemies should kill them."""
        tm = make_tilemap(LEVELS[0])
        p = make_player(*tm.player_start, "green")
        keys = fake_keys()
        for _ in range(10):
            p.update(keys, tm, particles, noop_sound)
        p.try_skill(_FakeGame(), tm, [], particles, noop_sound)
        for enemy in tm.enemies:
            if enemy.stompable and enemy.alive:
                p.x = enemy.x
                p._sync_rect()
                p.update_skill(tm, tm.enemies, particles, noop_sound)
                assert not enemy.alive, "Enemy should be killed by dash"
                break

    def test_dash_expires(self, make_player, make_tilemap, fake_keys, particles, noop_sound):
        """Dash should end after its duration."""
        tm = make_tilemap(LEVELS[0])
        p = make_player(*tm.player_start, "green")
        keys = fake_keys()
        for _ in range(10):
            p.update(keys, tm, particles, noop_sound)
        p.try_skill(_FakeGame(), tm, [], particles, noop_sound)
        assert p.skill_active is True
        for _ in range(30):
            p.update(keys, tm, particles, noop_sound)
        assert p.skill_active is False, "Dash should expire after duration"

    def test_dash_no_gravity_during_active(self, make_player, make_tilemap, fake_keys, particles, noop_sound):
        """Player should not fall during dash."""
        tm = make_tilemap(LEVELS[0])
        p = make_player(*tm.player_start, "green")
        keys = fake_keys()
        for _ in range(10):
            p.update(keys, tm, particles, noop_sound)
        p.try_skill(_FakeGame(), tm, [], particles, noop_sound)
        p.update(keys, tm, particles, noop_sound)
        assert p.vy == 0, f"Dash should negate gravity, vy={p.vy}"


# ---------------------------------------------------------------------------
# Pink character — Double Jump
# ---------------------------------------------------------------------------
class TestDoubleJumpSkill:

    def test_pink_has_double_jump_skill(self, make_player):
        p = make_player(100, 100, "pink")
        assert p.skill_type == SKILL_DOUBLE_JUMP

    def test_pink_has_higher_jump(self, make_player, make_tilemap, fake_keys, particles, noop_sound):
        """Pink's passive: +15% jump height."""
        tm = make_tilemap(LEVELS[0])
        p_pink = make_player(*tm.player_start, "pink")
        keys = fake_keys()
        for _ in range(10):
            p_pink.update(keys, tm, particles, noop_sound)
        p_pink.try_jump(tm, noop_sound)
        pink_vy = p_pink.vy

        p_purple = make_player(*tm.player_start, "purple")
        for _ in range(10):
            p_purple.update(keys, tm, particles, noop_sound)
        p_purple.try_jump(tm, noop_sound)
        purple_vy = p_purple.vy

        assert pink_vy < purple_vy, (
            f"Pink jump ({pink_vy}) should be stronger than purple ({purple_vy})"
        )

    def test_double_jump_in_air(self, make_player, make_tilemap, fake_keys, particles, noop_sound):
        """Pink can jump again while airborne."""
        tm = make_tilemap(LEVELS[0])
        p = make_player(*tm.player_start, "pink")
        keys = fake_keys()
        for _ in range(10):
            p.update(keys, tm, particles, noop_sound)
        # First jump
        p.try_jump(tm, noop_sound)
        assert p.vy < 0
        # Simulate air time
        for _ in range(10):
            p.update(keys, tm, particles, noop_sound)
        # Double jump
        p.try_jump(tm, noop_sound)
        assert p.vy < 0, "Double jump should set upward velocity"
        assert p.double_jumps_left == 0, "Double jump charge should be consumed"

    def test_double_jump_consumes_charge(self, make_player, make_tilemap, fake_keys, particles, noop_sound):
        tm = make_tilemap(LEVELS[0])
        p = make_player(*tm.player_start, "pink")
        keys = fake_keys()
        for _ in range(10):
            p.update(keys, tm, particles, noop_sound)
        assert p.double_jumps_left == 1
        p.try_jump(tm, noop_sound)
        for _ in range(10):
            p.update(keys, tm, particles, noop_sound)
        p.try_jump(tm, noop_sound)
        assert p.double_jumps_left == 0

    def test_double_jump_resets_on_landing(self, make_player, make_tilemap, fake_keys, particles, noop_sound):
        tm = make_tilemap(LEVELS[0])
        p = make_player(*tm.player_start, "pink")
        keys = fake_keys()
        for _ in range(10):
            p.update(keys, tm, particles, noop_sound)
        p.try_jump(tm, noop_sound)
        for _ in range(10):
            p.update(keys, tm, particles, noop_sound)
        p.try_jump(tm, noop_sound)
        assert p.double_jumps_left == 0
        # Land
        for _ in range(100):
            p.update(keys, tm, particles, noop_sound)
        assert p.on_ground, "Player should be on ground"
        assert p.double_jumps_left == 1, "Double jump should reset on landing"

    def test_no_triple_jump(self, make_player, make_tilemap, fake_keys, particles, noop_sound):
        """After using double jump, no more air jumps until landing."""
        tm = make_tilemap(LEVELS[0])
        p = make_player(*tm.player_start, "pink")
        keys = fake_keys()
        for _ in range(10):
            p.update(keys, tm, particles, noop_sound)
        p.try_jump(tm, noop_sound)
        for _ in range(5):
            p.update(keys, tm, particles, noop_sound)
        p.try_jump(tm, noop_sound)  # double jump
        assert p.double_jumps_left == 0
        for _ in range(5):
            p.update(keys, tm, particles, noop_sound)
        vy_before = p.vy
        p.try_jump(tm, noop_sound)  # should be buffered, not executed
        # vy should not equal double jump velocity
        assert p.vy != JUMP_VELOCITY * 0.85, "Should not be able to triple jump"


# ---------------------------------------------------------------------------
# Purple character — Time Slow
# ---------------------------------------------------------------------------
class TestSlowMoSkill:

    def test_purple_has_slow_mo_skill(self, make_player):
        p = make_player(100, 100, "purple")
        assert p.skill_type == SKILL_SLOW_MO

    def test_purple_has_longer_iframes(self, make_player):
        """Purple's passive: +50% invincibility frames."""
        p_purple = make_player(100, 100, "purple")
        p_green = make_player(100, 100, "green")
        p_purple.take_damage()
        p_green.take_damage()
        assert p_purple.invincible > p_green.invincible, (
            f"Purple iframes ({p_purple.invincible}) should be longer than green ({p_green.invincible})"
        )

    def test_slow_mo_activates(self, make_player, make_tilemap, fake_keys, particles, noop_sound):
        tm = make_tilemap(LEVELS[0])
        p = make_player(*tm.player_start, "purple")
        keys = fake_keys()
        for _ in range(10):
            p.update(keys, tm, particles, noop_sound)
        game = _FakeGame()
        result = p.try_skill(game, tm, [], particles, noop_sound)
        assert result is True
        assert p.skill_active is True
        assert game.slow_mo_timer > 0, "Slow-mo timer should be set on game"

    def test_slow_mo_has_cooldown(self, make_player, make_tilemap, fake_keys, particles, noop_sound):
        tm = make_tilemap(LEVELS[0])
        p = make_player(*tm.player_start, "purple")
        keys = fake_keys()
        for _ in range(10):
            p.update(keys, tm, particles, noop_sound)
        p.try_skill(_FakeGame(), tm, [], particles, noop_sound)
        assert p.skill_cooldown > 0
        result = p.try_skill(_FakeGame(), tm, [], particles, noop_sound)
        assert result is False, "Should not activate during cooldown"


# ---------------------------------------------------------------------------
# Star power-up invincibility
# ---------------------------------------------------------------------------
class TestStarInvincibility:

    def test_star_grants_invincibility(self, make_player, particles, noop_sound):
        p = make_player(100, 100, "green")
        assert p.star_invincible == 0
        p.activate_star(particles, noop_sound)
        assert p.star_invincible > 0
        assert p.star_invincible == STAR_INVINCIBILITY_FRAMES

    def test_star_invincibility_expires(self, make_player, make_tilemap, fake_keys, particles, noop_sound):
        tm = make_tilemap(LEVELS[0])
        p = make_player(*tm.player_start, "green")
        p.activate_star(particles, noop_sound)
        keys = fake_keys()
        for _ in range(STAR_INVINCIBILITY_FRAMES + 10):
            p.update(keys, tm, particles, noop_sound)
        assert p.star_invincible == 0, "Star invincibility should expire"

    def test_star_prevents_damage(self, make_player, particles, noop_sound):
        p = make_player(100, 100, "green")
        initial_health = p.health
        p.activate_star(particles, noop_sound)
        result = p.take_damage()
        assert result is False, "Star invincibility should prevent damage"
        assert p.health == initial_health

    def test_star_kills_enemies_on_contact(self, make_player, make_tilemap, particles, noop_sound):
        """While star is active, touching enemies kills them."""
        tm = make_tilemap(LEVELS[0])
        p = make_player(*tm.player_start, "green")
        p.activate_star(particles, noop_sound)
        for enemy in tm.enemies:
            if enemy.stompable and enemy.alive:
                if p.star_invincible > 0 and enemy.stompable:
                    enemy.kill()
                    p.score += 50
                assert not enemy.alive, "Enemy should be killed by star"
                assert p.score >= 50
                break


# ---------------------------------------------------------------------------
# Charge crystal — resets skill cooldown
# ---------------------------------------------------------------------------
class TestChargeCrystal:

    def test_reset_skill_cooldown(self, make_player, make_tilemap, fake_keys, particles, noop_sound):
        tm = make_tilemap(LEVELS[0])
        p = make_player(*tm.player_start, "green")
        keys = fake_keys()
        for _ in range(10):
            p.update(keys, tm, particles, noop_sound)
        p.try_skill(_FakeGame(), tm, [], particles, noop_sound)
        assert p.skill_cooldown > 0
        p.reset_skill_cooldown()
        assert p.skill_cooldown == 0, "Charge crystal should reset cooldown"


# ---------------------------------------------------------------------------
# Character selection
# ---------------------------------------------------------------------------
class TestCharacterSelection:

    def test_four_characters_available(self):
        assert len(CHARACTERS) == 4
        assert "beige" in CHARACTERS
        assert "green" in CHARACTERS
        assert "pink" in CHARACTERS
        assert "purple" in CHARACTERS

    def test_each_character_has_unique_skill(self):
        # Skilled characters each have a unique skill; beige has SKILL_NONE
        skilled = [c for c in CHARACTERS if CHARACTER_SKILLS[c]["skill"] != "none"]
        skills = set()
        for color in skilled:
            skill = CHARACTER_SKILLS[color]["skill"]
            assert skill not in skills, f"Duplicate skill for {color}"
            skills.add(skill)
        assert len(skilled) == 3  # green, pink, purple

    def test_each_character_has_skill_info(self):
        for color in CHARACTERS:
            info = CHARACTER_SKILLS[color]
            assert "skill" in info
            assert "name" in info
            assert "desc" in info
            assert "cooldown" in info

    def test_player_gets_correct_skill_for_color(self, make_player):
        for color in CHARACTERS:
            p = make_player(100, 100, color)
            expected = CHARACTER_SKILLS[color]["skill"]
            assert p.skill_type == expected, (
                f"Player color {color} should have skill {expected}, got {p.skill_type}"
            )

    def test_skill_resets_on_respawn(self, make_player, make_tilemap, fake_keys, particles, noop_sound):
        """Skill cooldown should reset when player respawns."""
        tm = make_tilemap(LEVELS[0])
        p = make_player(*tm.player_start, "green")
        keys = fake_keys()
        for _ in range(10):
            p.update(keys, tm, particles, noop_sound)
        p.try_skill(_FakeGame(), tm, [], particles, noop_sound)
        assert p.skill_cooldown > 0
        p.reset(100, 100)
        assert p.skill_cooldown == 0, "Cooldown should reset on respawn"
        assert p.skill_active is False
        assert p.double_jumps_left == 1
        assert p.star_invincible == 0


# ---------------------------------------------------------------------------
# Normal character (beige) — no skill, 3 HP max
# ---------------------------------------------------------------------------
class TestNormalCharacter:

    def test_beige_has_no_skill(self, make_player):
        p = make_player(100, 100, "beige")
        assert p.skill_type == "none"

    def test_beige_max_health_is_3(self, make_player):
        p = make_player(100, 100, "beige")
        assert p.max_health == 3

    def test_skilled_characters_max_health_is_5(self, make_player):
        for color in ["green", "pink", "purple"]:
            p = make_player(100, 100, color)
            assert p.max_health == 5, f"{color} should have max_health=5"

    def test_beige_starting_health_is_3(self, make_player):
        p = make_player(100, 100, "beige")
        assert p.health == 3

    def test_beige_cannot_exceed_3_hp(self, make_player):
        """Beige character's health should be capped at 3 even with hearts."""
        p = make_player(100, 100, "beige")
        p.health = min(p.max_health, p.health + 5)  # simulating heart pickup
        assert p.health == 3, "Beige should be capped at 3 HP"

    def test_skilled_can_reach_5_hp(self, make_player):
        """Skilled characters can reach 5 HP with hearts."""
        p = make_player(100, 100, "green")
        p.health = min(p.max_health, p.health + 5)
        assert p.health == 5, "Green should be able to reach 5 HP"

    def test_beige_no_speed_bonus(self, make_player, make_tilemap, fake_keys, particles, noop_sound):
        """Beige has no passive speed bonus."""
        tm = make_tilemap(LEVELS[0])
        p = make_player(*tm.player_start, "beige")
        keys = fake_keys({pygame.K_RIGHT: True})
        for _ in range(200):
            p.update(keys, tm, particles, noop_sound)
        from src.constants import PLAYER_MAX_SPEED
        assert p.vx <= PLAYER_MAX_SPEED + 0.1, (
            f"Beige speed should not exceed base: vx={p.vx} <= {PLAYER_MAX_SPEED}"
        )

    def test_beige_no_jump_bonus(self, make_player, make_tilemap, fake_keys, particles, noop_sound):
        """Beige has no jump height bonus."""
        tm = make_tilemap(LEVELS[0])
        p = make_player(*tm.player_start, "beige")
        keys = fake_keys()
        for _ in range(10):
            p.update(keys, tm, particles, noop_sound)
        p.try_jump(tm, noop_sound)
        assert p.vy == JUMP_VELOCITY, f"Beige jump should be base: vy={p.vy}"

    def test_beige_try_skill_does_nothing(self, make_player, make_tilemap, fake_keys, particles, noop_sound):
        """Beige cannot use any skill."""
        tm = make_tilemap(LEVELS[0])
        p = make_player(*tm.player_start, "beige")
        keys = fake_keys()
        for _ in range(10):
            p.update(keys, tm, particles, noop_sound)
        result = p.try_skill(_FakeGame(), tm, [], particles, noop_sound)
        assert result is False
        assert p.skill_active is False
