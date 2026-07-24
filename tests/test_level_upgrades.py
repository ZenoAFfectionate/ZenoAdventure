"""Acceptance tests for the IMPROVEMENT.md section-4 level & gadget upgrades.

Covers:
  * Desert Dash conveyor teaching combo (right belt -> pit -> left belt ->
    spike -> safe ground, first left belt never followed by a pit)
  * Crystal Cave shallow-then-deep pool and the guaranteed exit ledge
  * Lava Lake flush-spring launch over the final lava pit
  * Sky Temple anti-bypass rework (recovery islands, vertical shuttles,
    upper-route lock & door)
  * Vertical moving platforms carrying the player
  * Slow-mo stretching fire warnings without extending the burn
  * Character-specific tutorial hints, the one-time star rule hint, and
    the tutorial on/off setting
"""

import pygame

from src.levels import LEVELS
from src.constants import TILE_SIZE

SKY = LEVELS[4]


# ---------------------------------------------------------------------------
# 4.2 Desert Dash — conveyor teaching combo
# ---------------------------------------------------------------------------
class TestDesertConveyorCombo:

    def test_combo_layout_order(self, make_tilemap):
        """safe ground -> right belt -> small pit -> left belt -> spike."""
        tm = make_tilemap(LEVELS[1])
        assert all(tm.conveyors.get((c, 9)) == 1 for c in range(32, 36))
        assert all(tm.conveyors.get((c, 9)) == -1 for c in range(38, 41))
        # The small pit between the two belts.
        for c in (36, 37):
            assert not tm.has_ground_below(c, 9, max_depth=3)
        # Single spike after the left belt.
        assert (42, 8) in tm.hazards

    def test_first_left_belt_not_followed_by_pit(self, make_tilemap):
        """The first leftward belt must have solid ground right after it."""
        tm = make_tilemap(LEVELS[1])
        first = min(c for (c, _r), d in tm.conveyors.items() if d == -1)
        after = first + 3  # the belt is three tiles wide
        assert tm.has_ground_below(after, 9, max_depth=1)


# ---------------------------------------------------------------------------
# 4.3 Crystal Cave — pool teaching curve
# ---------------------------------------------------------------------------
class TestCrystalPool:

    def test_shallow_shelf_before_deep_zone(self, make_tilemap):
        """Waist-deep shelf (cols 43-44) teaches the slow-down first."""
        tm = make_tilemap(LEVELS[2])
        for c in (43, 44):
            assert (c, 10) in tm.solids            # raised shelf floor
            assert (c, 8) in tm.water
            assert (c, 9) in tm.water
            assert (c, 10) not in tm.water         # only waist deep
        special = set(tm.flag_positions)  # the checkpoint flag displaces water
        for c in range(45, 49):
            assert (c, 11) in tm.solids            # deep-zone floor
            for r in (8, 9, 10):
                assert (
                    (c, r) in tm.water
                    or (c, r) in tm.oneways
                    or (c, r) in special
                )

    def test_submerged_ledge_guarantees_exit(self, make_tilemap):
        """A one-way ledge level with the exit lip means no drowning trap."""
        tm = make_tilemap(LEVELS[2])
        assert (47, 9) in tm.oneways
        assert (48, 9) in tm.oneways


# ---------------------------------------------------------------------------
# 4.4 Lava Lake — spring launch rhythm change
# ---------------------------------------------------------------------------
class TestLavaSpringLaunch:

    def test_flush_spring_before_final_pit(self, make_tilemap):
        tm = make_tilemap(LEVELS[3])
        assert (95, 9) in tm.springs
        assert (96, 9) in tm.hazards  # lava pit right after the spring

    def test_spring_not_adjacent_to_fire_hazard(self, make_tilemap):
        """The launch pad itself is safe ground."""
        tm = make_tilemap(LEVELS[3])
        assert (95, 9) in tm.solids
        assert (95, 9) not in tm.hazards


# ---------------------------------------------------------------------------
# 4.5 Sky Temple — anti-bypass rework
# ---------------------------------------------------------------------------
class TestSkyAntiBypass:

    def test_lock_and_door_on_upper_route(self, make_tilemap):
        tm = make_tilemap(SKY)
        dcol, drow = tm.door_pos
        assert drow <= 8, "door must sit on the aerial route, not the floor"
        for (_c, r) in tm.locks:
            assert r <= 8, "lock must sit on the aerial route"

    def test_bottom_voids_are_unjumpable(self, make_tilemap):
        """Running right along the bottom can never cross a void (>= 5 tiles)."""
        tm = make_tilemap(SKY)
        row = 11
        c = 0
        gaps = []
        while c < tm.width:
            if (c, row) not in tm.solids:
                start = c
                while c < tm.width and (c, row) not in tm.solids:
                    c += 1
                gaps.append((start, c - 1))
            c += 1
        assert gaps, "expected bottom voids"
        for start, end in gaps:
            assert end - start + 1 >= 5, (
                f"bottom gap cols {start}-{end} is jumpable — bypass possible"
            )

    def test_every_recovery_island_has_a_spring(self, make_tilemap):
        """No soft locks: each bottom island can launch the player back up."""
        tm = make_tilemap(SKY)
        row = 11
        islands = []
        c = 0
        while c < tm.width:
            if (c, row) in tm.solids:
                start = c
                while c < tm.width and (c, row) in tm.solids:
                    c += 1
                islands.append((start, c - 1))
            c += 1
        assert len(islands) == 4, f"expected 4 recovery islands, got {islands}"
        for start, end in islands:
            assert any(
                start <= sc <= end for (sc, sr) in tm.springs if sr == row
            ), f"island cols {start}-{end} has no recovery spring"

    def test_island_springs_reach_aerial_route(self, make_tilemap):
        """Spring apex from the floor must clear the lowest aerial platforms."""
        from src.constants import SPRING_VELOCITY, GRAVITY
        apex_px = SPRING_VELOCITY ** 2 / (2 * GRAVITY)
        floor_top = 11 * TILE_SIZE
        apex_y = floor_top - apex_px
        # Lowest aerial platforms are at row 8 (top edge y = 8 * TILE_SIZE).
        assert apex_y < 8 * TILE_SIZE

    def test_vertical_shuttles_debut_slow(self, make_tilemap):
        tm = make_tilemap(SKY)
        vertical = [mp for mp in tm.moving_platforms if mp.axis == "y"]
        assert len(vertical) >= 2, "expected vertical shuttle variants"
        vertical.sort(key=lambda mp: mp.start_x)
        assert vertical[0].speed <= 0.8, "first vertical shuttle must be slow"

    def test_shuttle_paths_never_push_into_geometry(self, make_tilemap):
        """Swept paths (plus rider headroom) stay clear of solids and bounds."""
        for i, lvl in enumerate(LEVELS):
            tm = make_tilemap(lvl)
            for mp in tm.moving_platforms:
                if mp.axis == "y":
                    col = int(mp.start_x // TILE_SIZE)
                    top_row = int(mp.min_y // TILE_SIZE) - 1
                    bot_row = int(mp.max_y // TILE_SIZE) + 1
                    assert 0 <= top_row and bot_row < tm.height, (
                        f"Level {i+1}: vertical shuttle leaves map bounds"
                    )
                    for r in range(top_row, bot_row + 1):
                        assert not tm.is_solid_at(col, r), (
                            f"Level {i+1}: vertical shuttle path blocked at "
                            f"({col},{r})"
                        )
                else:
                    row = int(mp.rect.y // TILE_SIZE)
                    c0 = int(mp.min_x // TILE_SIZE) - 1
                    c1 = int(mp.max_x // TILE_SIZE) + 1
                    for c in range(max(0, c0), min(tm.width - 1, c1) + 1):
                        assert not tm.is_solid_at(c, row), (
                            f"Level {i+1}: horizontal shuttle path blocked at "
                            f"({c},{row})"
                        )

    def test_riding_vertical_shuttle_carries_player(
            self, make_tilemap, make_player, fake_keys, particles, noop_sound):
        """Standing on a rising shuttle lifts the player smoothly."""
        tm = make_tilemap(SKY)
        mp = next(m for m in tm.moving_platforms if m.axis == "y")
        player = make_player(mp.rect.centerx, mp.rect.top - 58, "beige")
        keys = fake_keys()
        for _ in range(5):
            player.update(keys, tm, particles, noop_sound)
            mp.update()
        assert player.riding is mp, "player should settle onto the shuttle"
        start_y = player.y
        for _ in range(120):
            player.update(keys, tm, particles, noop_sound)
            mp.update()
        assert player.y < start_y - TILE_SIZE, (
            "shuttle should carry the rider up at least one tile"
        )

    def test_jumping_off_clears_riding(
            self, make_tilemap, make_player, fake_keys, particles, noop_sound):
        tm = make_tilemap(SKY)
        mp = next(m for m in tm.moving_platforms if m.axis == "y")
        player = make_player(mp.rect.centerx, mp.rect.top - 58, "beige")
        keys = fake_keys()
        for _ in range(5):
            player.update(keys, tm, particles, noop_sound)
            mp.update()
        assert player.riding is mp
        player.try_jump(tm, noop_sound)
        assert player.riding is None


# ---------------------------------------------------------------------------
# 4.4 Fire patch vs slow-mo
# ---------------------------------------------------------------------------
class TestFirePatchSlowMo:

    def test_slow_mo_stretches_warning_not_burn(self, tmp_path):
        from src.game import Game

        game = Game(progress_path=str(tmp_path / "save.json"))
        game.start_level(3)
        enemy = next(e for e in game.tilemap.enemies if e.etype == "fire_slime")
        enemy.kill()
        game._on_enemy_defeated(enemy, "stomp")
        patch = game.fire_patches[0]
        burn0, warn0 = patch.timer, patch.warning
        # Eight slow-mo frames: the warning ticks on only one in four.
        for i in range(8):
            patch.update(slow_warning=(i % 4 != 0))
        assert patch.timer == burn0 - 8, "burn time must run in real time"
        assert patch.warning == warn0 - 2, "warning should stretch 4x"

    def test_warning_still_real_time_without_slow_mo(self, tmp_path):
        from src.game import Game

        game = Game(progress_path=str(tmp_path / "save.json"))
        game.start_level(3)
        enemy = next(e for e in game.tilemap.enemies if e.etype == "fire_slime")
        enemy.kill()
        game._on_enemy_defeated(enemy, "stomp")
        patch = game.fire_patches[0]
        warn0 = patch.warning
        for _ in range(8):
            patch.update(slow_warning=False)
        assert patch.warning == warn0 - 8


# ---------------------------------------------------------------------------
# 4.1 Tutorial hints
# ---------------------------------------------------------------------------
class TestTutorialHints:

    def test_skill_hint_matches_character(self, tmp_path):
        from src.game import Game, SKILL_HINTS

        for color, expected in SKILL_HINTS.items():
            g = Game(progress_path=str(tmp_path / f"save_{color}.json"))
            g.character_color = color
            g.start_level(0)
            assert any(h["text"] == expected for h in g._tutorial_hints), (
                f"{color}: missing skill hint {expected!r}"
            )

    def test_beige_hint_is_classic_challenge(self, tmp_path):
        from src.game import Game

        g = Game(progress_path=str(tmp_path / "save.json"))
        g.character_color = "beige"
        g.start_level(0)
        assert any("Classic Challenge" in h["text"] for h in g._tutorial_hints)

    def test_skill_hint_placed_before_first_crystal(self, tmp_path):
        from src.game import Game

        g = Game(progress_path=str(tmp_path / "save.json"))
        g.start_level(0)
        crystal_col = min(
            item.col for item in g.tilemap.collectibles if item.kind == "c"
        )
        skill_hints = [
            h for h in g._tutorial_hints if "Skill" in h["text"]
            or "Classic" in h["text"]
        ]
        assert skill_hints
        for hint in skill_hints:
            assert hint["x"] < crystal_col * TILE_SIZE

    def test_star_pickup_shows_rule_hint_once(self, tmp_path):
        from src.game import Game, STAR_RULE_HINT

        g = Game(progress_path=str(tmp_path / "save.json"))
        g.start_level(4)  # Sky Temple has a star on the main route
        star = next(i for i in g.tilemap.collectibles if i.kind == "*")
        g.player.x, g.player.y = star.x, star.y
        g.player._sync_rect()
        g._update_playing()
        assert g._star_hint_shown
        assert g.active_tutorial_hint == STAR_RULE_HINT

    def test_tutorial_setting_suppresses_hints(self, tmp_path):
        from src.game import Game

        g = Game(progress_path=str(tmp_path / "save.json"))
        g.show_tutorial = False
        g.start_level(0)
        g.player.x = g._tutorial_hints[0]["x"] + 10
        g._update_playing()
        assert g.active_tutorial_hint is None

    def test_controls_screen_toggles_tutorial_setting(self, tmp_path):
        from src.game import Game

        g = Game(progress_path=str(tmp_path / "save.json"))
        g.state = g.S_CONTROLS
        before = g.show_tutorial
        g._handle_keydown(pygame.K_t)
        assert g.show_tutorial is not before
        assert g.progress.data["settings"]["tutorial_hints"] == g.show_tutorial
