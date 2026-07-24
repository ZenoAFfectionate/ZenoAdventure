"""Programmatic playtest harness for ZenoAdventure.

Unlike the older hand-rolled collision loops, this harness drives the REAL
game loop (``Game._update_playing``) with scripted keyboard input, so a
playthrough exercises exactly the same code a human player would: physics,
fire patches, the guardian, hints, key/lock/door gating, lives and
respawning.

Typical usage::

    game = Game(progress_path=str(tmp_path / "save.json"))
    result = simulate_playthrough(game, level_index=0, character="beige")
    assert result.reached
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pygame

from src.constants import TILE_SIZE
from src.levels import LEVELS


# ---------------------------------------------------------------------------
# Scripted input
# ---------------------------------------------------------------------------
class ScriptedKeys(dict):
    """Dict that mimics ``pygame.key.get_pressed()`` with False defaults."""

    def __getitem__(self, key):
        return self.get(key, False)


# ---------------------------------------------------------------------------
# Playthrough result
# ---------------------------------------------------------------------------
@dataclass
class PlayResult:
    """Outcome of a simulated playthrough."""

    reached: bool = False            # walked through the exit door
    game_over: bool = False          # ran out of lives
    frames: int = 0
    elapsed: float = 0.0             # in-game seconds (game.level_time)
    final_x: float = 0.0             # final player x in tiles
    deaths: int = 0                  # lives lost (game.level_deaths)
    damage_taken: int = 0            # successful take_damage calls
    key_collected: bool = False
    boss_defeated: bool | None = None
    checkpoints_hit: set = field(default_factory=set)
    hints_shown: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Scripted AI player
# ---------------------------------------------------------------------------
def apply_boss_ai(boss, player, keys, tilemap, sound):
    """Guardian-fight behaviour: dodge the landing marker through the open
    right side, wait nearby, jump the shockwaves, and hop on the guardian
    while it is vulnerable — the same counters a human uses."""
    if not boss or boss.defeated or not boss.activated:
        # Restore the default hold-right state (also repairs keys after a
        # respawn that happened mid-dodge).
        keys[pygame.K_RIGHT] = True
        keys[pygame.K_LEFT] = False
        return
    if boss.state in (boss.WARNING, boss.FALLING):
        if abs(player.center_x - boss.target_x) < 110:
            # Escape the landing marker through the open right side...
            keys[pygame.K_RIGHT] = True
            keys[pygame.K_LEFT] = False
        else:
            # ...then wait nearby so the vulnerable window stays reachable.
            keys[pygame.K_RIGHT] = False
            keys[pygame.K_LEFT] = False
    elif boss.state in (boss.CHARGE, boss.SHOCKWAVE, boss.SQUASHED):
        # Hold position and jump the waves.
        keys[pygame.K_RIGHT] = False
        keys[pygame.K_LEFT] = False
    elif boss.state == boss.VULNERABLE:
        # Move toward the guardian, then hop on its head
        if boss.center_x > player.center_x + 20:
            keys[pygame.K_RIGHT] = True
            keys[pygame.K_LEFT] = False
        elif boss.center_x < player.center_x - 20:
            keys[pygame.K_RIGHT] = False
            keys[pygame.K_LEFT] = True
        else:
            keys[pygame.K_RIGHT] = False
            keys[pygame.K_LEFT] = False
        if player.on_ground and abs(boss.center_x - player.center_x) < 96:
            player.try_jump(tilemap, sound)
            keys[pygame.K_SPACE] = True
    else:
        keys[pygame.K_RIGHT] = True
        keys[pygame.K_LEFT] = False
    # Jump over incoming shockwaves
    if player.on_ground and boss.wave_threat(player.x):
        player.try_jump(tilemap, sound)
        keys[pygame.K_SPACE] = True


def default_ai(game: "Game", keys: ScriptedKeys):
    """Per-frame decision: hold RIGHT, auto-jump gaps/hazards/enemies,
    handle the guardian fight.  Mirrors a decent casual player."""
    tm = game.tilemap
    player = game.player
    cy = int(player.feet_y // TILE_SIZE)
    if player.on_ground and not player.spring_bounce:
        # Jump earlier when faster (skill speed bonus)
        look_ahead = 70 if abs(player.vx) > 7 else 60
        ahead_col = int((player.x + look_ahead) // TILE_SIZE)
        has_ground = tm.has_ground_below(ahead_col, cy, max_depth=3)
        hazard = any(
            (ahead_col, r) in tm.hazards
            for r in range(max(0, cy - 1), min(tm.height, cy + 2))
        )
        # Springs bounce automatically — no need to jump
        spring_ahead = any(
            (ahead_col, r) in tm.springs
            for r in range(max(0, cy - 1), min(tm.height, cy + 2))
        )
        enemy_ahead = any(
            e.alive and abs(e.x - player.x) < 80 and e.x > player.x
            for e in tm.enemies
        )
        if (not has_ground or hazard or enemy_ahead) and not spring_ahead:
            player.try_jump(tm, game.play_sound)
            keys[pygame.K_SPACE] = True   # hold for full jump height
        else:
            keys.pop(pygame.K_SPACE, None)
    elif player.on_ground:
        keys.pop(pygame.K_SPACE, None)
    else:
        # Keep holding jump while ascending (variable jump height)
        if player.vy < 0:
            keys[pygame.K_SPACE] = True
        else:
            keys.pop(pygame.K_SPACE, None)

    apply_boss_ai(tm.boss, player, keys, tm, game.play_sound)


# ---------------------------------------------------------------------------
# Playthrough driver
# ---------------------------------------------------------------------------
def simulate_playthrough(
    game: "Game",
    *,
    level_index: int | None = None,
    character: str | None = None,
    max_frames: int = 8000,
    ai=default_ai,
) -> PlayResult:
    """Play one level with the real game loop and scripted input.

    ``game`` must be an initialised ``Game``.  When ``level_index`` is
    given, the level is (re)started first; otherwise the current level is
    played as-is.  Returns a rich ``PlayResult`` for assertions.
    """
    if character is not None:
        game.character_color = character
    if level_index is not None:
        game.start_level(level_index)
    assert game.state == game.S_PLAYING, "game must be in the playing state"

    result = PlayResult()
    keys = ScriptedKeys({pygame.K_RIGHT: True})

    # Instrument damage/respawn counters without touching game code
    player = game.player
    real_take_damage = player.take_damage

    def counting_take_damage(ignore_star: bool = False):
        took = real_take_damage(ignore_star)
        if took:
            result.damage_taken += 1
        return took

    player.take_damage = counting_take_damage

    real_get_pressed = pygame.key.get_pressed
    pygame.key.get_pressed = lambda: keys
    try:
        for frame in range(1, max_frames + 1):
            ai(game, keys)
            game._update_playing()

            result.frames = frame
            result.checkpoints_hit.add(game.tilemap.checkpoint)
            if game.active_tutorial_hint and (
                    not result.hints_shown
                    or result.hints_shown[-1] != game.active_tutorial_hint):
                result.hints_shown.append(game.active_tutorial_hint)

            if game.state in (game.S_LEVEL_COMPLETE, game.S_VICTORY):
                result.reached = True
                break
            if game.state == game.S_GAME_OVER:
                result.game_over = True
                break
    finally:
        pygame.key.get_pressed = real_get_pressed
        player.take_damage = real_take_damage

    result.elapsed = game.level_time
    result.final_x = game.player.x / TILE_SIZE if game.player else 0.0
    result.deaths = game.level_deaths
    result.key_collected = game.tilemap.has_key
    if game.tilemap.boss is not None:
        result.boss_defeated = game.tilemap.boss.defeated
    return result


def simulate_campaign(
    game: "Game",
    *,
    character: str = "beige",
    max_frames_per_level: int = 8000,
    ai=default_ai,
) -> list[PlayResult]:
    """Play the whole campaign (levels 1..N) like a real session.

    Lives carry across levels exactly as in the real game.  Stops early if
    a level cannot be completed.
    """
    game.character_color = character
    game.total_score = 0
    game.total_time = 0.0
    results: list[PlayResult] = []
    for index in range(len(LEVELS)):
        game.start_level(index)
        result = simulate_playthrough(
            game, max_frames=max_frames_per_level, ai=ai
        )
        results.append(result)
        if not result.reached:
            break
    return results
