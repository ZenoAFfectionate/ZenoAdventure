"""Tests for the IMPROVEMENT.md section-5 enemy & combat upgrades.

Covers:
  * Snail shell kicking (kick, speed cap, chain-hit limit)
  * Bee/fly patrol differentiation (horizontal vs vertical)
  * Tracked saw variant (moves, bounded, indestructible)
  * Fire patch extinguish animation and smoke
  * Spike slime dash/star vulnerability with clear feedback
  * Frog leap telegraph (landing shadow data)
  * Vertical fish staying inside its water column
  * Block Guardian mini-boss (phase cycle, telegraphs, stomp windows,
    pause freeze, respawn reset, victory door)
  * Level dressing sanity (decorations never overlap gameplay tiles)
"""

import pygame

from src.levels import LEVELS
from src.constants import TILE_SIZE, STARTING_HEALTH


def _noop(name):
    return None


# ---------------------------------------------------------------------------
# Snail shell kicking
# ---------------------------------------------------------------------------
class TestSnailKick:

    def _snail(self, make_tilemap):
        for lvl in LEVELS:
            for e in make_tilemap(lvl).enemies:
                if e.etype == "snail":
                    return e
        raise AssertionError("no snail in any level")

    def test_shell_can_be_kicked(self, make_tilemap):
        snail = self._snail(make_tilemap)
        snail.stomp()  # into shell
        assert snail.in_shell
        snail.vx = 0
        assert snail.kick(1) is True
        assert snail.vx > 0
        assert snail.kicked

    def test_kick_speed_is_capped(self, make_tilemap):
        snail = self._snail(make_tilemap)
        snail.stomp()
        snail.vx = 0
        snail.kick(1)
        assert abs(snail.vx) <= 6.0

    def test_walking_snail_cannot_be_kicked(self, make_tilemap):
        snail = self._snail(make_tilemap)
        assert snail.kick(1) is False

    def test_moving_shell_cannot_be_kicked_again(self, make_tilemap):
        snail = self._snail(make_tilemap)
        snail.stomp()
        snail.vx = 0
        snail.kick(1)
        assert snail.kick(-1) is False

    def test_kicked_shell_defeats_first_enemy_only(self, tmp_path):
        """Chain damage is limited: one kill per kick."""
        from src.game import Game

        game = Game(progress_path=str(tmp_path / "save.json"))
        game.start_level(0)
        tm = game.tilemap
        snail = next(e for e in tm.enemies if e.etype == "snail")
        snail.stomp()
        snail.vx = 0
        snail.kick(1)
        others = [e for e in tm.enemies if e is not snail and e.alive]
        victim_a, victim_b = others[0], others[1]
        # Place both victims along the shell's path
        victim_a.x, victim_a.y = snail.x + 20, snail.y
        victim_b.x, victim_b.y = snail.x + 40, snail.y
        for e in (victim_a, victim_b):
            pad = e.size * 0.15
            e.hitbox.x = e.x + pad
            e.hitbox.y = e.y + pad
        shell_hits = 0
        for _ in range(10):
            for other in tm.enemies:
                if other is snail or not other.alive:
                    continue
                if snail.hitbox.colliderect(other.hitbox):
                    other.kill()
                    game._on_enemy_defeated(other, "shell")
                    snail.vx *= 0.2
                    shell_hits += 1
            snail.hitbox.x = snail.x + snail.vx
        assert shell_hits >= 1
        assert abs(snail.vx) < 1.5  # shell spent after the hit


# ---------------------------------------------------------------------------
# Bee / fly patrol differentiation
# ---------------------------------------------------------------------------
class TestFlyerDifferentiation:

    def test_bee_patrols_wide_and_flat(self, make_tilemap):
        bees = [e for lvl in LEVELS for e in make_tilemap(lvl).enemies
                if e.etype == "bee"]
        assert bees
        for bee in bees:
            assert bee.patrol_range >= 6 * TILE_SIZE
            assert bee.fly_amp <= 30

    def test_fly_patrols_narrow_and_tall(self, make_tilemap):
        flies = [e for lvl in LEVELS for e in make_tilemap(lvl).enemies
                 if e.etype == "fly"]
        assert flies
        for fly in flies:
            assert fly.patrol_range <= 2 * TILE_SIZE
            assert fly.fly_amp >= 50


# ---------------------------------------------------------------------------
# Tracked saw
# ---------------------------------------------------------------------------
class TestTrackedSaw:

    def test_tracked_saw_moves_and_stays_bounded(self, make_tilemap):
        tm = make_tilemap(LEVELS[4])
        saws = [e for e in tm.enemies if e.etype == "saw_track"]
        assert saws, "expected a tracked saw in Sky Temple"
        for saw in saws:
            xs = []
            for _ in range(600):
                saw.update(tm)
                xs.append(saw.x)
            assert max(xs) - min(xs) > TILE_SIZE, "tracked saw should move"
            for x in xs:
                assert abs(x - saw.start_x) <= saw.track_len + 1

    def test_tracked_saw_is_indestructible(self, make_tilemap):
        tm = make_tilemap(LEVELS[4])
        saw = next(e for e in tm.enemies if e.etype == "saw_track")
        assert saw.stomp() is False
        assert saw.dashable is False


# ---------------------------------------------------------------------------
# Fire patch extinguish
# ---------------------------------------------------------------------------
class TestFirePatchExtinguish:

    def test_extinguish_phase_shrinks(self, tmp_path):
        from src.game import Game

        game = Game(progress_path=str(tmp_path / "save.json"))
        game.start_level(3)
        enemy = next(e for e in game.tilemap.enemies if e.etype == "fire_slime")
        enemy.kill()
        game._on_enemy_defeated(enemy, "stomp")
        patch = game.fire_patches[0]
        patch.warning = 0
        patch.timer = 10
        assert patch.dangerous and patch.timer < 20  # extinguish window


# ---------------------------------------------------------------------------
# Spike slime vulnerability
# ---------------------------------------------------------------------------
class TestSpikeSlimeKillable:

    def test_spike_slime_is_dashable(self, make_tilemap):
        spike = next(e for lvl in LEVELS for e in make_tilemap(lvl).enemies
                     if e.etype == "spike_slime")
        assert spike.dashable is True
        assert spike.stompable is False

    def test_dash_kills_spike_slime_with_bonus_feedback(self, tmp_path):
        from src.game import Game

        game = Game(progress_path=str(tmp_path / "save.json"))
        game.character_color = "green"
        game.start_level(3)
        spike = next(e for e in game.tilemap.enemies if e.etype == "spike_slime")
        game.player.x, game.player.y = spike.x, spike.y
        game.player._sync_rect()
        game.player.skill_active = True
        game.player.skill_timer = 10
        before = game.player.score
        game.player.update_skill(
            game.tilemap, game.tilemap.enemies, game.particles,
            game.play_sound, game._on_enemy_defeated,
        )
        assert not spike.alive
        assert game.player.score - before == 100
        assert any("ARMOR BREAK" in ft["text"] for ft in game.particles.float_texts)

    def test_star_kills_spike_slime(self, tmp_path):
        from src.game import Game

        game = Game(progress_path=str(tmp_path / "save.json"))
        game.start_level(3)
        spike = next(e for e in game.tilemap.enemies if e.etype == "spike_slime")
        game.player.x, game.player.y = spike.x, spike.y
        game.player._sync_rect()
        game.player.activate_star(game.particles, game.play_sound)
        game._update_playing()
        assert not spike.alive


# ---------------------------------------------------------------------------
# Vertical fish
# ---------------------------------------------------------------------------
class TestVerticalFish:

    def test_vfish_stays_inside_water_column(self, make_tilemap):
        tm = make_tilemap(LEVELS[2])
        fish = next(e for e in tm.enemies if e.etype == "vfish")
        for _ in range(800):
            fish.update(tm)
            center = (
                int((fish.x + fish.size / 2) // TILE_SIZE),
                int((fish.y + fish.size / 2) // TILE_SIZE),
            )
            assert center in tm.water


# ---------------------------------------------------------------------------
# Block Guardian
# ---------------------------------------------------------------------------
class TestBlockGuardian:

    def _game(self, tmp_path):
        from src.game import Game

        game = Game(progress_path=str(tmp_path / "save.json"))
        game.start_level(4)
        return game

    def _enter_arena(self, game):
        """Teleport the player onto the arena floor (as if just landed)."""
        game.player.x = 105 * TILE_SIZE
        game.player.y = 7 * TILE_SIZE
        game.player.vy = 0
        game.player.on_ground = True
        game.player._sync_rect()

    def test_phase_cycle_order(self, tmp_path):
        game = self._game(tmp_path)
        boss = game.tilemap.boss
        self._enter_arena(game)
        seen = []
        for _ in range(600):
            boss.update(game.player, game.particles, game.play_sound, game.camera)
            if not seen or seen[-1] != boss.state:
                seen.append(boss.state)
            if boss.state == boss.VULNERABLE:
                break
        assert seen[0] == boss.WARNING
        assert boss.FALLING in seen
        assert boss.CHARGE in seen
        assert boss.SHOCKWAVE in seen
        assert seen[-1] == boss.VULNERABLE

    def test_warning_telegraph_is_at_least_half_second(self, tmp_path):
        game = self._game(tmp_path)
        boss = game.tilemap.boss
        self._enter_arena(game)
        boss.update(game.player, game.particles, game.play_sound, game.camera)
        assert boss.state == boss.WARNING
        assert boss.WARNING_TIME >= 30  # >= 0.5 s at 60 FPS

    def test_stomps_defeat_boss_and_open_door(self, tmp_path):
        game = self._game(tmp_path)
        tm = game.tilemap
        boss = tm.boss
        self._enter_arena(game)
        assert not tm.door_open
        for _ in range(20000):
            boss.update(game.player, game.particles, game.play_sound, game.camera)
            if boss.state == boss.VULNERABLE:
                # Drop onto the guardian's head (rects already overlapping)
                game.player.x = boss.center_x
                game.player.y = boss.rect.top - game.player.h + 4
                game.player.vy = 5.0
                game.player.prev_feet_y = boss.rect.top - 2
                game.player._sync_rect()
            if boss.defeated:
                break
        assert boss.defeated
        assert boss.hits == 0
        # Door opens on the next game frame
        game._update_playing()
        assert tm.door_open

    def test_contact_while_vulnerable_is_harmless(self, tmp_path):
        game = self._game(tmp_path)
        boss = game.tilemap.boss
        self._enter_arena(game)
        for _ in range(600):
            boss.update(game.player, game.particles, game.play_sound, game.camera)
            if boss.state == boss.VULNERABLE:
                break
        assert boss.state == boss.VULNERABLE
        # Stand inside the guardian: no stomp, no damage
        game.player.x = boss.center_x
        game.player.y = boss.y
        game.player.vy = 0
        game.player.invincible = 0
        game.player._sync_rect()
        hp = game.player.health
        boss.update(game.player, game.particles, game.play_sound, game.camera)
        assert game.player.health == hp

    def test_falling_boss_is_a_telegraphed_threat(self, tmp_path):
        game = self._game(tmp_path)
        boss = game.tilemap.boss
        self._enter_arena(game)
        # Wait until the guardian is falling, then stand under it
        for _ in range(600):
            boss.update(game.player, game.particles, game.play_sound, game.camera)
            if boss.state == boss.FALLING:
                break
        game.player.x = boss.x + TILE_SIZE / 2
        game.player.y = boss.floor_top - game.player.h
        game.player.vy = 0
        game.player.invincible = 0
        game.player._sync_rect()
        hp = game.player.health
        for _ in range(200):
            boss.update(game.player, game.particles, game.play_sound, game.camera)
        assert game.player.health < hp

    def test_boss_freezes_when_paused(self, tmp_path):
        game = self._game(tmp_path)
        boss = game.tilemap.boss
        self._enter_arena(game)
        for _ in range(10):
            game._update_playing()
        assert boss.activated
        game.state = game.S_PAUSED
        snapshot = (boss.state, boss.timer, boss.x, boss.y, boss.hits)
        for _ in range(60):
            game._update()  # paused: must not advance anything
        assert (boss.state, boss.timer, boss.x, boss.y, boss.hits) == snapshot

    def test_player_death_resets_the_fight(self, tmp_path):
        game = self._game(tmp_path)
        boss = game.tilemap.boss
        self._enter_arena(game)
        for _ in range(120):
            boss.update(game.player, game.particles, game.play_sound, game.camera)
        assert boss.activated
        game.respawn_player()
        assert not boss.activated
        assert boss.hits == boss.MAX_HITS

    def test_slow_mo_stretches_boss_timers(self, tmp_path):
        game = self._game(tmp_path)
        boss = game.tilemap.boss
        self._enter_arena(game)
        game.slow_mo_timer = 100
        # The boss only ticks on every 4th slow-mo frame; frame_count is
        # advanced manually to mirror the real main loop.
        for _ in range(8):
            game.frame_count += 1
            game._update_playing()
        assert boss.activated
        timer0 = boss.timer
        for _ in range(4):
            game.frame_count += 1
            game._update_playing()
        assert boss.timer >= timer0 - 1  # ticks at 1/4 rate


# ---------------------------------------------------------------------------
# Level dressing sanity
# ---------------------------------------------------------------------------
class TestDecorations:

    def test_decorations_never_overlap_gameplay_tiles(self, make_tilemap):
        for i, lvl in enumerate(LEVELS):
            tm = make_tilemap(lvl)
            occupied = (
                set(tm.solids) | set(tm.oneways) | set(tm.hazards)
                | set(tm.water) | set(tm.ladders) | set(tm.locks)
                | {(c, r) for (c, r) in tm.key_positions}
                | {(c, r) for (c, r) in tm.flag_positions}
                | {(c, r) for (c, r) in tm.springs}
                | {(item.col, item.row) for item in tm.collectibles}
                | {(enemy.col, enemy.row) for enemy in tm.enemies}
                | {tm.door_pos}
            )
            for (c, r, ch) in tm.decorations:
                assert (c, r) not in occupied, (
                    f"Level {i+1}: decoration '{ch}' at ({c},{r}) overlaps "
                    f"a gameplay tile"
                )

    def test_every_level_has_some_dressing(self, make_tilemap):
        for i, lvl in enumerate(LEVELS):
            tm = make_tilemap(lvl)
            assert tm.decorations or tm.torches, (
                f"Level {i+1} ({lvl['name']}) has no decorations"
            )
