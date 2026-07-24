"""Focused regression tests for the expanded level mechanics."""

import pygame

from src.constants import TILE_SIZE
from src.levels import LEVELS


def test_every_new_mechanic_is_used(make_tilemap):
    maps = [make_tilemap(level) for level in LEVELS]
    assert any(tm.conveyors for tm in maps)
    assert any(tm.ladders for tm in maps)
    assert any(tm.moving_platforms for tm in maps)
    assert any(tm.water for tm in maps)
    assert any(tm.conveyors.values() and -1 in tm.conveyors.values() for tm in maps)
    assert any(any(item.kind == "c" for item in tm.collectibles) for tm in maps)
    types = {enemy.etype for tm in maps for enemy in tm.enemies}
    assert {"fire_slime", "spike_slime", "frog"} <= types


def test_underwater_gem_keeps_its_water_cell(make_tilemap):
    tm = make_tilemap(LEVELS[2])
    gem = next(item for item in tm.collectibles if item.col == 45 and item.row == 8)
    assert gem.kind == "b"
    assert (gem.col, gem.row) in tm.water


def test_conveyor_only_pushes_grounded_player(
        make_tilemap, make_player, fake_keys, particles, noop_sound):
    tm = make_tilemap(LEVELS[1])
    (col, row), direction = next(iter(tm.conveyors.items()))
    player = make_player(col * TILE_SIZE + TILE_SIZE / 2, (row - 1) * TILE_SIZE)
    player.y = row * TILE_SIZE - player.h
    player._sync_rect()
    before = player.x
    player.update(fake_keys(), tm, particles, noop_sound)
    assert player.x > before if direction > 0 else player.x < before


def test_charge_crystal_resets_cooldown(make_player):
    player = make_player(0, 0, "green")
    player.skill_cooldown = 300
    player.reset_skill_cooldown()
    assert player.skill_cooldown == 0


def test_spike_slime_cannot_be_stomped(make_tilemap):
    enemies = [e for level in LEVELS for e in make_tilemap(level).enemies]
    spike = next(e for e in enemies if e.etype == "spike_slime")
    assert spike.stomp() is False
    assert spike.alive


def test_fish_remains_inside_water(make_tilemap):
    tm = make_tilemap(LEVELS[2])
    fish = next(enemy for enemy in tm.enemies if enemy.etype == "fish")
    for _ in range(600):
        fish.update(tm)
        center = (
            int((fish.x + fish.size / 2) // TILE_SIZE),
            int((fish.y + fish.size / 2) // TILE_SIZE),
        )
        assert center in tm.water


def test_stomped_fire_slime_leaves_warned_fire_patch(tmp_path):
    from src.game import Game

    game = Game(progress_path=str(tmp_path / "save.json"))
    game.start_level(3)
    enemy = next(e for e in game.tilemap.enemies if e.etype == "fire_slime")
    enemy.kill()
    game._on_enemy_defeated(enemy, "stomp")
    assert len(game.fire_patches) == 1
    patch = game.fire_patches[0]
    assert not patch.dangerous
    for _ in range(18):
        patch.update()
    assert patch.dangerous


def test_dash_kill_does_not_leave_fire_patch(tmp_path):
    from src.game import Game

    game = Game(progress_path=str(tmp_path / "save.json"))
    game.start_level(3)
    enemy = next(e for e in game.tilemap.enemies if e.etype == "fire_slime")
    enemy.kill()
    game._on_enemy_defeated(enemy, "dash")
    assert game.fire_patches == []


def test_tutorial_hint_expires():
    from src.game import Game

    game = Game()
    game.start_level(0)
    game.player.x = game._tutorial_hints[0]["x"]
    game._update_playing()
    assert game.active_tutorial_hint
    for _ in range(180):
        game._update_playing()
    assert game.active_tutorial_hint is None


def test_side_wall_does_not_change_vertical_position(
        make_tilemap, make_player, particles, noop_sound):
    tm = make_tilemap(LEVELS[0])
    player = make_player(tm.pixel_w - 19, 2 * TILE_SIZE)
    player.vy = -5
    player._sync_rect()
    before = player.y
    player._collide_y(tm, player.feet_y, particles, noop_sound)
    assert player.y == before
    assert player.vy == -5


def test_high_speed_movement_is_clamped_to_both_boundaries(
        make_tilemap, make_player):
    tm = make_tilemap(LEVELS[0])
    player = make_player(*tm.player_start)

    player.x = -500
    player.vx = -100
    player._sync_rect()
    player._collide_x(tm)
    assert player.rect.left >= 0
    assert player.vx == 0

    player.x = tm.pixel_w + 500
    player.vx = 100
    player._sync_rect()
    player._collide_x(tm)
    assert player.rect.right <= tm.pixel_w
    assert player.vx == 0
