"""Progression persistence, level rating, and level-select tests."""

import json

import pygame

from src.levels import LEVELS
from src.progression import ProgressionStore


def _result(**overrides):
    result = {
        "name": "Green Hills",
        "time": 42.5,
        "score": 600,
        "total_score": 600,
        "collection_ratio": 1.0,
        "stars": 3,
        "badges": {"complete": True, "exploration": True, "skill": True},
        "character": "green",
    }
    result.update(overrides)
    return result


def test_progression_round_trip_and_best_values(tmp_path):
    path = tmp_path / "save.json"
    store = ProgressionStore(str(path), len(LEVELS))
    store.record_level(0, _result())
    store.record_level(
        0,
        _result(time=55.0, score=900, total_score=900,
                collection_ratio=0.5, stars=2, character="pink"),
    )

    loaded = ProgressionStore(str(path), len(LEVELS))
    record = loaded.level_record(0)
    assert record["best_time"] == 42.5
    assert record["best_score"] == 900
    assert record["best_collection"] == 1.0
    assert record["stars"] == 3
    assert record["characters"] == ["green", "pink"]
    assert loaded.data["unlocked_level"] == 1


def test_different_runs_combine_independent_badges(tmp_path):
    path = tmp_path / "save.json"
    store = ProgressionStore(str(path), len(LEVELS))
    store.record_level(
        0,
        _result(stars=2, badges={
            "complete": True, "exploration": True, "skill": False,
        }),
    )
    store.record_level(
        0,
        _result(stars=2, badges={
            "complete": True, "exploration": False, "skill": True,
        }),
    )
    assert store.level_record(0)["stars"] == 3


def test_corrupt_save_is_backed_up_and_reset(tmp_path):
    path = tmp_path / "save.json"
    path.write_text("{not json", encoding="utf-8")
    store = ProgressionStore(str(path), len(LEVELS))
    assert store.data["unlocked_level"] == 0
    assert (tmp_path / "save.json.corrupt").exists()


def test_save_is_valid_json_and_leaves_no_temp_file(tmp_path):
    path = tmp_path / "save.json"
    store = ProgressionStore(str(path), len(LEVELS))
    store.record_level(0, _result())
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 1
    assert not (tmp_path / "save.json.tmp").exists()


def test_new_progress_fields_are_persisted(tmp_path):
    path = tmp_path / "save.json"
    store = ProgressionStore(str(path), len(LEVELS))
    store.data["settings"]["difficulty"] = "hard"
    unlocked = store.unlock_achievement("combo_master")
    assert unlocked["name"] == "Air Combo"
    assert store.unlock_achievement("combo_master") is None

    loaded = ProgressionStore(str(path), len(LEVELS))
    assert loaded.data["settings"]["difficulty"] == "hard"
    assert loaded.data["achievements"]["combo_master"]["unlocked"] is True


def test_level_completion_awards_each_star(tmp_path):
    from src.game import Game

    game = Game(progress_path=str(tmp_path / "save.json"))
    game.start_level(0)
    for item in game.tilemap.collectibles:
        item.collected = True
    game.level_time = LEVELS[0]["time_limit"] - 1
    game.complete_level()
    assert game._level_result["stars"] == 3


def test_death_removes_skill_star(tmp_path):
    from src.game import Game

    game = Game(progress_path=str(tmp_path / "save.json"))
    game.start_level(0)
    game.level_deaths = 1
    game.level_time = 1
    game.complete_level()
    assert game._level_result["stars"] == 1


def test_level_select_only_starts_unlocked_level(tmp_path):
    from src.game import Game

    game = Game(progress_path=str(tmp_path / "save.json"))
    game.state = game.S_LEVEL_SELECT
    game.level_select_index = 4
    game._handle_keydown(pygame.K_RETURN)
    assert game.state == game.S_LEVEL_SELECT

    game.progress.data["unlocked_level"] = 2
    game.level_select_index = 2
    game._handle_keydown(pygame.K_RETURN)
    assert game.state == game.S_PLAYING
    assert game.current_level == 2


def test_all_enemy_defeat_paths_share_scoring(tmp_path):
    from src.game import Game

    game = Game(progress_path=str(tmp_path / "save.json"))
    game.start_level(0)
    enemy = game.tilemap.enemies[0]
    before = game.player.score
    game._on_enemy_defeated(enemy, "dash")
    assert game.player.score == before + 50
    assert game.level_enemies_defeated == 1


def test_star_absorbs_one_hazard_hit(make_tilemap, make_player, fake_keys,
                                     particles, noop_sound):
    tm = make_tilemap(LEVELS[3])
    col, row = next(iter(tm.hazards))
    player = make_player(col * 64 + 32, row * 64, "green")
    player.star_invincible = 100
    health = player.health
    player.update(fake_keys(), tm, particles, noop_sound)
    assert player.health == health
    assert player.star_invincible == 0
    assert player.invincible > 0


def test_star_does_not_protect_from_pits(make_player):
    player = make_player()
    player.star_invincible = 100
    assert player.take_damage(ignore_star=True)
    assert player.health == 2
