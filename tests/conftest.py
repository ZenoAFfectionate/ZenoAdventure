"""
conftest.py - Shared pytest fixtures for headless pygame testing.

Sets up a dummy SDL video/audio driver so all tests can run without
a real display or sound device.
"""

import os
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path setup — ensure the project root is importable
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Headless SDL environment (must be set *before* pygame.init)
# ---------------------------------------------------------------------------
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _pygame_init():
    """Initialise pygame once for the entire test session."""
    pygame.init()
    # Minimal display surface required by many pygame operations
    pygame.display.set_mode((128, 128))
    yield
    pygame.quit()


@pytest.fixture
def tile_size():
    from src.constants import TILE_SIZE
    return TILE_SIZE


@pytest.fixture
def make_tilemap():
    """Factory fixture: call make_tilemap(level_data) -> TileMap."""
    from src.game import TileMap

    def _factory(level_data):
        return TileMap(level_data)
    return _factory


@pytest.fixture
def make_player():
    """Factory fixture: call make_player(x, y, color) -> Player."""
    from src.entities import Player

    def _factory(x=0, y=0, color="beige"):
        return Player(x, y, color)
    return _factory


@pytest.fixture
def fake_keys():
    """Return a dict-like object that mimics pygame.key.get_pressed()."""
    class _Keys(dict):
        def __getitem__(self, k):
            return self.get(k, False)
    return _Keys


@pytest.fixture
def noop_sound():
    """A no-op sound function for entity update calls."""
    return lambda name: None


@pytest.fixture
def particles():
    from src.entities import ParticleSystem
    return ParticleSystem()
