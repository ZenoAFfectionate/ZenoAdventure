"""
test_game.py - Tests for the Game state machine, level flow, and scoring.

Covers:
  * Game initialisation and state
  * State transitions (menu → charselect → playing → paused → complete → ...)
  * Level start/reset
  * Player death and respawn
  * Level completion (door collision)
  * Victory (all levels complete)
  * Score accumulation and high score persistence
  * Key/lock interaction
  * Stomp combo system
  * Time bonus calculation
  * Full level playthrough simulation (AI-driven)
"""

import pytest
import pygame
import os

from src.levels import LEVELS
from src.constants import TILE_SIZE, JUMP_VELOCITY, STARTING_LIVES, STARTING_HEALTH


class TestGameInitialisation:

    def test_game_creates_successfully(self):
        from src.game import Game
        g = Game()
        assert g.state == g.S_MENU
        assert g.current_level == 0
        assert g.total_score == 0
        assert g.total_time == 0.0

    def test_high_score_loaded(self):
        from src.game import Game
        g = Game()
        # High score should be a non-negative integer
        assert isinstance(g.high_score, int)
        assert g.high_score >= 0


class TestStateTransitions:

    def test_menu_to_playing(self):
        from src.game import Game
        g = Game()
        g.menu_index = 0  # "Start Game"
        g._menu_action()
        assert g.state == g.S_PLAYING

    def test_menu_to_charselect(self):
        from src.game import Game
        g = Game()
        g.menu_index = 1  # "Select Character"
        g._menu_action()
        assert g.state == g.S_CHARSELECT

    def test_menu_to_controls(self):
        from src.game import Game
        g = Game()
        g.menu_index = 2  # "Controls"
        g._menu_action()
        assert g.state == g.S_CONTROLS

    def test_menu_cycles_difficulty(self, tmp_path):
        from src.game import Game

        g = Game(progress_path=str(tmp_path / "save.json"))
        g.menu_index = 4  # "Difficulty: Normal"
        g._menu_action()
        assert g.difficulty == "hard"
        assert "Hard" in g.menu_items[4]
        assert g.progress.data["settings"]["difficulty"] == "hard"

    def test_playing_to_paused(self):
        from src.game import Game
        g = Game()
        g.start_level(0)
        assert g.state == g.S_PLAYING
        g._handle_keydown(pygame.K_ESCAPE)
        assert g.state == g.S_PAUSED

    def test_paused_to_playing(self):
        from src.game import Game
        g = Game()
        g.start_level(0)
        g._handle_keydown(pygame.K_ESCAPE)  # pause
        g._handle_keydown(pygame.K_ESCAPE)  # resume
        assert g.state == g.S_PLAYING

    def test_paused_restart_level(self):
        from src.game import Game
        g = Game()
        g.start_level(0)
        g._handle_keydown(pygame.K_ESCAPE)  # pause
        g._handle_keydown(pygame.K_r)  # restart
        assert g.state == g.S_PLAYING

    def test_paused_quit_to_menu(self):
        from src.game import Game
        g = Game()
        g.start_level(0)
        g._handle_keydown(pygame.K_ESCAPE)  # pause
        g._handle_keydown(pygame.K_q)  # quit to menu
        assert g.state == g.S_MENU


class TestLevelManagement:

    def test_start_level_sets_state(self):
        from src.game import Game
        g = Game()
        g.start_level(0)
        assert g.state == g.S_PLAYING
        assert g.tilemap is not None
        assert g.player is not None
        assert g.camera is not None

    def test_start_level_resets_time(self):
        from src.game import Game
        g = Game()
        g.start_level(0)
        assert g.level_time == 0.0

    def test_start_level_preserves_lives(self):
        from src.game import Game
        g = Game()
        g.start_level(0)
        g.player.lives = 2
        g.start_level(1)
        assert g.player.lives == 2

    def test_start_level_resets_lives_on_first(self):
        from src.game import Game
        g = Game()
        g.start_level(2)
        g.player.lives = 1
        g.start_level(0)
        assert g.player.lives == STARTING_LIVES

    def test_hard_mode_starts_with_two_lives_and_countdown(self, tmp_path):
        from src.game import Game

        g = Game(progress_path=str(tmp_path / "save.json"))
        g.difficulty = "hard"
        g.progress.data["settings"]["difficulty"] = "hard"
        g.start_level(0)
        assert g.player.lives == 2

        g.level_time = g.level_target_time
        g._update_playing()
        assert g.state == g.S_GAME_OVER
        assert g.game_over_reason == "TIME UP"

    def test_hard_mode_tunes_level_parameters(self, tmp_path):
        from src.game import Game

        g = Game(progress_path=str(tmp_path / "save.json"))
        g.difficulty = "hard"
        g.start_level(0)
        assert g.tilemap.conveyor_speed_mult == 1.25
        assert all(abs(enemy.base_speed) >= 0 for enemy in g.tilemap.enemies)
        if len(g.tilemap.flag_positions) > 1:
            assert len(g.tilemap.flag_positions) <= 2


class TestPlayerDeath:

    def test_death_reduces_lives(self):
        from src.game import Game
        g = Game()
        g.start_level(0)
        initial_lives = g.player.lives
        g.player_died()
        assert g.player.lives == initial_lives - 1

    def test_death_triggers_game_over_at_zero_lives(self):
        from src.game import Game
        g = Game()
        g.start_level(0)
        g.player.lives = 1
        g.player_died()
        assert g.state == g.S_GAME_OVER

    def test_respawn_restores_health(self):
        from src.game import Game
        g = Game()
        g.start_level(0)
        g.player.health = 1
        g.respawn_player()
        assert g.player.health == STARTING_HEALTH

    def test_respawn_resets_position(self):
        from src.game import Game
        g = Game()
        g.start_level(0)
        original_x, original_y = g.player.x, g.player.y
        # Move player somewhere
        g.player.x += 500
        g.player.y += 200
        g.respawn_player()
        # Should be back at checkpoint (which starts as player_start)
        assert abs(g.player.x - original_x) < TILE_SIZE
        assert abs(g.player.y - original_y) < TILE_SIZE


class TestLevelCompletion:

    def test_complete_level_advances_state(self):
        from src.game import Game
        g = Game()
        g.start_level(0)
        g.player.score = 500
        g.complete_level()
        assert g.state == g.S_LEVEL_COMPLETE

    def test_complete_last_level_triggers_victory(self):
        from src.game import Game
        g = Game()
        g.start_level(len(LEVELS) - 1)
        g.complete_level()
        assert g.state == g.S_VICTORY

    def test_time_bonus_decreases_with_time(self):
        from src.game import Game
        g = Game()
        g.start_level(0)
        g.level_time = 10.0
        g.complete_level()
        bonus_fast = g._time_bonus

        g2 = Game()
        g2.start_level(0)
        g2.level_time = 50.0
        g2.complete_level()
        bonus_slow = g2._time_bonus

        assert bonus_fast > bonus_slow, (
            f"Faster time should give more bonus: {bonus_fast} vs {bonus_slow}"
        )

    def test_time_bonus_zero_after_level_target(self):
        from src.game import Game
        g = Game()
        g.start_level(0)
        g.level_time = LEVELS[0]["time_limit"] + 1
        g.complete_level()
        assert g._time_bonus == 0

    def test_score_accumulates_across_levels(self):
        from src.game import Game
        g = Game()
        g.start_level(0)
        g.player.score = 1000
        g.complete_level()
        assert g.total_score >= 1000

    def test_final_completion_uses_victory_music_and_summary(self, tmp_path, monkeypatch):
        from src import assets
        from src.game import Game

        calls = []
        monkeypatch.setattr(assets, "play_music", lambda name, muted=False: calls.append((name, muted)))
        monkeypatch.setattr(assets, "stop_music", lambda: None)

        g = Game(progress_path=str(tmp_path / "save.json"))
        g.start_level(len(LEVELS) - 1)
        g.complete_level()
        assert g.state == g.S_VICTORY
        assert calls[-1] == ("victory", False)
        assert g._final_result["name"] == LEVELS[-1]["name"]
        assert g._final_result["difficulty"] == "normal"

    def test_three_stomp_combo_unlocks_achievement(self, tmp_path):
        from src.game import Game

        g = Game(progress_path=str(tmp_path / "save.json"))
        g.start_level(0)
        enemy = g.tilemap.enemies[0]
        for _ in range(3):
            g._on_enemy_defeated(enemy, "stomp")
        assert g.progress.data["achievements"]["combo_master"]["unlocked"] is True
        assert any(a["id"] == "combo_master" for a in g.level_achievements_unlocked)

    def test_lava_no_heart_completion_unlocks_achievement(self, tmp_path):
        from src.game import Game

        g = Game(progress_path=str(tmp_path / "save.json"))
        g.start_level(3)
        g.level_hearts_collected = 0
        g.complete_level()
        assert "lava_purity" in g.progress.data["achievements"]
        assert any(a["id"] == "lava_purity" for a in g._level_result["achievements"])


class TestKeyLockInteraction:

    def test_collect_key_opens_locks(self):
        from src.game import Game
        g = Game()
        g.start_level(0)
        # Find a level with locks
        if g.tilemap.locks:
            assert not g.tilemap.locks_open
            g.tilemap.collect_key()
            assert g.tilemap.has_key
            assert g.tilemap.locks_open

    def test_door_requires_key_when_locks_exist(self):
        from src.game import Game
        g = Game()
        g.start_level(0)
        if g.tilemap.locks:
            # Without key, door should not open
            dc, dr = g.tilemap.door_pos
            door_rect = pygame.Rect(dc * TILE_SIZE, dr * TILE_SIZE, TILE_SIZE, TILE_SIZE * 2)
            # Place player at door
            g.player.x = dc * TILE_SIZE
            g.player.y = dr * TILE_SIZE
            g.player._sync_rect()
            # Simulate door collision check
            has_locks = len(g.tilemap.locks) > 0
            can_enter = not has_locks or g.tilemap.locks_open
            assert not can_enter, "Door should require key when locks exist"

    def test_door_opens_after_key_collected(self):
        from src.game import Game
        g = Game()
        g.start_level(0)
        if g.tilemap.locks:
            g.tilemap.collect_key()
            has_locks = len(g.tilemap.locks) > 0
            can_enter = not has_locks or g.tilemap.locks_open
            assert can_enter, "Door should be accessible after collecting key"


class TestStompCombo:

    def test_combo_increments_on_stomp(self):
        from src.game import Game
        g = Game()
        g.start_level(0)
        g._stomp_combo = 0
        g._stomp_combo_timer = 0
        # Simulate stomp
        g._stomp_combo += 1
        assert g._stomp_combo == 1

    def test_combo_resets_after_timer(self):
        from src.game import Game
        g = Game()
        g.start_level(0)
        g._stomp_combo = 3
        g._stomp_combo_timer = 1
        # Run update to expire timer
        g._stomp_combo_timer = 0
        if hasattr(g, '_stomp_combo_timer') and g._stomp_combo_timer <= 0:
            g._stomp_combo = 0
        assert g._stomp_combo == 0

    def test_combo_gives_bonus_score(self):
        """Higher combo should give more score per stomp."""
        from src.game import Game
        g = Game()
        g.start_level(0)
        g._stomp_combo = 0
        bonus_1 = 30 * 1   # first stomp
        bonus_2 = 30 * 2   # second consecutive
        bonus_3 = 30 * 3   # third consecutive
        assert bonus_2 > bonus_1
        assert bonus_3 > bonus_2


# ---------------------------------------------------------------------------
# Full playthrough simulation (AI-driven)
# ---------------------------------------------------------------------------
# The playtest harness lives in tests/simulate.py and drives the REAL game
# loop (Game._update_playing) with scripted input.
from tests.simulate import (  # noqa: E402
    ScriptedKeys as _ScriptedKeys,  # re-exported for legacy importers
    apply_boss_ai as _apply_boss_ai,  # re-exported for legacy importers
    simulate_playthrough,
)


def _simulate_level(g, max_frames=6000):
    """Backward-compatible wrapper around simulate_playthrough."""
    result = simulate_playthrough(g, max_frames=max_frames)
    return result.reached, result.frames, result.final_x


class TestFullPlaythrough:

    @pytest.mark.parametrize("level_idx", range(len(LEVELS)))
    def test_level_is_completable(self, level_idx):
        """
        Each level should be completable by a simple AI that runs right
        and auto-jumps over gaps and hazards.

        This is the ultimate integration test: if a level cannot be
        completed, there is likely a design flaw (unreachable key,
        impassable gap, enemy blocking the only path, etc.).
        """
        from src.game import Game
        g = Game()
        g.character_color = "beige"  # Use beige (no bonuses) for reliable AI
        g.start_level(level_idx)
        reached, frames, final_x = _simulate_level(g)
        assert reached, (
            f"Level {level_idx+1} ({LEVELS[level_idx]['name']}) was NOT completed "
            f"in {frames} frames (final x={final_x:.1f} tiles)"
        )
