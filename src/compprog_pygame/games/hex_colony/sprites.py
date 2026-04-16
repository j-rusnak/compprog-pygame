"""Sprite loading and caching system for Hex Colony.

Sprites are loaded from ``assets/sprites/`` and cached at multiple zoom
levels.  Each sprite is a PNG file with transparency.

Directory layout::

    assets/sprites/
        buildings/
            camp.png
            house.png
            woodcutter.png
            quarry.png
            gatherer.png
            storage.png
            overcrowded.png
        overlays/
            tree_canopy.png
            tree_conifer.png
            tree_round.png
            rock.png
            bush.png
            grass.png
            crystal_iron.png
            crystal_copper.png
        people/
            person_idle.png
            person_gather.png

To replace a sprite, drop a new PNG file with the same name into the
appropriate subdirectory.  Sprites are loaded once at startup and then
scaled per-zoom as needed.

The base sprite resolution matches a hex radius of 32 px at zoom 1.0.
"""

from __future__ import annotations

from pathlib import Path

import pygame

from compprog_pygame.settings import ASSET_DIR

SPRITE_DIR = ASSET_DIR / "sprites"


def _ensure_dirs() -> None:
    """Create sprite subdirectories if they don't exist."""
    for sub in ("buildings", "overlays", "people"):
        (SPRITE_DIR / sub).mkdir(parents=True, exist_ok=True)


class SpriteSheet:
    """Loads and caches a single sprite at multiple zoom levels."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._base: pygame.Surface | None = None
        self._cache: dict[tuple[int, int], pygame.Surface] = {}

    def _load(self) -> pygame.Surface:
        if self._base is None:
            self._base = pygame.image.load(str(self.path)).convert_alpha()
        return self._base

    def get(self, width: int, height: int) -> pygame.Surface:
        """Return the sprite scaled to (width, height), cached."""
        key = (width, height)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        base = self._load()
        scaled = pygame.transform.smoothscale(base, (max(1, width), max(1, height)))
        self._cache[key] = scaled
        return scaled

    def get_at_zoom(self, zoom: float) -> pygame.Surface:
        """Return the sprite scaled for the given camera zoom."""
        base = self._load()
        w = max(1, int(base.get_width() * zoom))
        h = max(1, int(base.get_height() * zoom))
        return self.get(w, h)

    @property
    def base_size(self) -> tuple[int, int]:
        base = self._load()
        return base.get_width(), base.get_height()


class SpriteManager:
    """Central sprite registry — loads all sprites from disk once."""

    def __init__(self) -> None:
        _ensure_dirs()
        self._sprites: dict[str, SpriteSheet] = {}
        self._loaded = False

    def load_all(self) -> None:
        """Scan the sprite directory and load every PNG found."""
        if self._loaded:
            return
        self._loaded = True
        if not SPRITE_DIR.exists():
            return
        for png in SPRITE_DIR.rglob("*.png"):
            # Key = relative path without extension, using / separator
            rel = png.relative_to(SPRITE_DIR).with_suffix("")
            key = str(rel).replace("\\", "/")
            self._sprites[key] = SpriteSheet(png)

    def get(self, key: str) -> SpriteSheet | None:
        """Retrieve a sprite by key (e.g. ``'buildings/camp'``)."""
        return self._sprites.get(key)

    def has(self, key: str) -> bool:
        return key in self._sprites

    @property
    def available_keys(self) -> list[str]:
        return list(self._sprites.keys())


# Module-level singleton
sprites = SpriteManager()
