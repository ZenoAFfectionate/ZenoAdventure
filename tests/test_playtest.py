"""End-to-end playtest scenarios built on the shared harness
(tests/simulate.py).

These tests play the game the way a player would — through the real game
loop — and assert outcomes that matter for playability:

  * every character can complete every level (no skill gating)
  * the full campaign is finishable and ends in victory
  * levels are completable without a game over (lives are sufficient)
  * the guardian must fall before the exit opens
  * checkpoints actually resume progress after a fall
  * tutorial/star hints appear during real play
  * levels can be finished comfortably within their target times
"""

import pytest

from src.levels import LEVELS
from src.constants import CHARACTERS
from tests.simulate import simulate_playthrough, simulate_campaign


def _game(tmp_path, name="save.json"):
    from src.game import Game

    return Game(progress_path=str(tmp_path / name))


# ---------------------------------------------------------------------------
# Character x level completion matrix
# ---------------------------------------------------------------------------
class TestCompletionMatrix:

    @pytest.mark.parametrize("character", CHARACTERS)
    @pytest.mark.parametrize("level_idx", range(len(LEVELS)))
    def test_character_can_complete_level(self, tmp_path, character, level_idx):
        """No level may require a specific character skill (hard gate)."""
        game = _game(tmp_path, f"save_{character}_{level_idx}.json")
        result = simulate_playthrough(
            game, level_index=level_idx, character=character, max_frames=8000
        )
        assert result.reached, (
            f"{character} could not complete Level {level_idx + 1} "
            f"({LEVELS[level_idx]['name']}): final x={result.final_x:.1f}, "
            f"deaths={result.deaths}, game_over={result.game_over}"
        )


# ---------------------------------------------------------------------------
# Campaign flow
# ---------------------------------------------------------------------------
class TestCampaign:

    @pytest.mark.parametrize("character", CHARACTERS)
    def test_full_campaign_reaches_victory(self, tmp_path, character):
        """A real session: all five levels in sequence, ending in victory."""
        game = _game(tmp_path, f"save_{character}.json")
        results = simulate_campaign(game, character=character)
        assert len(results) == len(LEVELS)
        assert all(r.reached for r in results), (
            f"{character} campaign stalled: "
            f"{[r.reached for r in results]}"
        )
        assert game.state == game.S_VICTORY

    def test_levels_do_not_end_in_game_over(self, tmp_path):
        """Beige should finish every level with lives to spare — the
        difficulty curve must not force a game over on a decent player."""
        game = _game(tmp_path)
        for i in range(len(LEVELS)):
            game.start_level(i)
            result = simulate_playthrough(game, max_frames=8000)
            assert result.reached, f"Level {i + 1} was not completed"
            assert not result.game_over, (
                f"Level {i + 1} ({LEVELS[i]['name']}) ended in game over — "
                f"too punishing (deaths={result.deaths})"
            )


# ---------------------------------------------------------------------------
# Guardian gating
# ---------------------------------------------------------------------------
class TestGuardianGate:

    def test_boss_defeated_before_exit(self, tmp_path):
        """The Sky Temple playthrough must defeat the guardian first."""
        game = _game(tmp_path)
        result = simulate_playthrough(game, level_index=4, character="beige")
        assert result.reached
        assert result.boss_defeated is True, (
            "exit door was reached while the guardian was still standing"
        )
        assert game.tilemap.door_open

    def test_door_stays_sealed_while_boss_lives(self, tmp_path):
        """Touching the door with the guardian alive must not complete."""
        game = _game(tmp_path)
        game.start_level(4)
        tm = game.tilemap
        tm.collect_key()  # locks open; only the guardian seals the door now
        dc, dr = tm.door_pos
        game.player.x = dc * 64
        game.player.y = dr * 64
        game.player._sync_rect()
        game._update_playing()
        assert game.state == game.S_PLAYING, (
            "level completed while the guardian was alive"
        )
        assert game.door_sealed_msg > 0


# ---------------------------------------------------------------------------
# Checkpoint recovery
# ---------------------------------------------------------------------------
class TestCheckpointRecovery:

    def test_death_resumes_at_latest_flag_not_start(self, tmp_path):
        """Falling after touching a later flag must respawn there."""
        game = _game(tmp_path)
        game.start_level(0)
        tm = game.tilemap
        # Walk the player into the last flag, then drop them into the void
        last_flag = max(tm.flag_positions, key=lambda fr: fr[0])
        game.player.x = last_flag[0] * 64
        game.player.y = last_flag[1] * 64
        game.player._sync_rect()
        game._update_playing()  # touch the flag
        assert tm.checkpoint == (last_flag[0] * 64, last_flag[1] * 64)
        game.player.y = tm.pixel_h + 200  # fall out
        game.player._sync_rect()
        game._update_playing()
        assert game.player.health == 3  # respawned with fresh health
        assert abs(game.player.x - last_flag[0] * 64) < 64, (
            "player respawned at the start instead of the latest checkpoint"
        )


# ---------------------------------------------------------------------------
# Tutorial hints in real play
# ---------------------------------------------------------------------------
class TestHintsInPlay:

    def test_star_rule_hint_appears_in_green_hills(self, tmp_path):
        """Green Hills has a star on the main route; picking it up must
        show the one-time rule hint during a real playthrough."""
        from src.game import STAR_RULE_HINT

        game = _game(tmp_path)
        result = simulate_playthrough(game, level_index=0, character="beige")
        assert result.reached
        assert STAR_RULE_HINT in result.hints_shown

    def test_tutorial_hints_fire_in_order_on_level_one(self, tmp_path):
        game = _game(tmp_path)
        result = simulate_playthrough(game, level_index=0, character="green")
        assert result.reached
        assert len(result.hints_shown) >= 3, (
            f"expected several tutorial hints, got {result.hints_shown}"
        )
        assert any("Dash" in text for text in result.hints_shown), (
            "Green's dash skill hint never appeared during play"
        )

    def test_hints_stay_off_when_disabled(self, tmp_path):
        game = _game(tmp_path)
        game.show_tutorial = False
        result = simulate_playthrough(game, level_index=0, character="beige")
        assert result.reached
        assert result.hints_shown == []


# ---------------------------------------------------------------------------
# Target times leave headroom
# ---------------------------------------------------------------------------
class TestTargetTimeHeadroom:

    @pytest.mark.parametrize("level_idx", range(len(LEVELS)))
    def test_ai_finishes_well_under_target(self, tmp_path, level_idx):
        """The scripted AI is slower than a decent speedrunner; if it can
        finish inside the target time, humans have comfortable headroom."""
        game = _game(tmp_path, f"save_{level_idx}.json")
        result = simulate_playthrough(
            game, level_index=level_idx, character="beige", max_frames=8000
        )
        assert result.reached
        target = LEVELS[level_idx]["time_limit"]
        assert result.elapsed < target, (
            f"Level {level_idx + 1}: AI needed {result.elapsed:.1f}s "
            f"> target {target}s — target time is too tight"
        )
