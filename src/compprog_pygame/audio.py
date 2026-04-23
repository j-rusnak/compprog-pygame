"""Lightweight background-music framework.

Goals
-----
* One ``MusicManager`` singleton (``music``) that any screen, cutscene,
  or game can call into without having to know about ``pygame.mixer``
  bookkeeping.
* Logical *tracks* (``"menu"``, ``"cutscene"``, ``"gameplay"``)
  resolved at runtime to the first matching file in
  ``assets/audio/music/<id>.<ext>`` for a configurable extension list.
* Crossfade between tracks; idempotent ``play()`` (re-requesting the
  current track does nothing).
* Graceful no-op when the mixer fails to initialize (CI, headless,
  audio device missing) or when the requested track has no audio file
  on disk.  This means the framework is safe to wire in *before* any
  music files exist — drop a ``menu.ogg`` into
  ``assets/audio/music/`` later and it just starts working.

Adding a new track
------------------
1. Pick a logical id (e.g. ``"victory"``).
2. Drop ``assets/audio/music/victory.ogg`` (or ``.mp3`` / ``.wav``).
3. Call ``music.play("victory")`` from wherever you want it.

Playlists (multiple tracks per id)
----------------------------------
If a *directory* exists at ``assets/audio/music/<id>/`` containing one
or more audio files, ``play(id)`` treats it as a playlist: tracks are
played in sorted filename order and loop back to the first track when
the last one finishes.  This is how ``"gameplay"`` is expected to be
used — drop any number of files into ``assets/audio/music/gameplay/``
and they will rotate on repeat.

For playlists to advance, the host loop must call ``music.tick()``
once per frame (the hex-colony game loop already does so).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pygame

from compprog_pygame.settings import ASSET_DIR

log = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────

#: Where music files are looked up.  Override by editing this constant
#: or by passing a custom directory to ``MusicManager.__init__``.
MUSIC_DIR: Path = ASSET_DIR / "audio" / "music"

#: Extensions probed in order.  ``.ogg`` is recommended (small, looped
#: cleanly by SDL2_mixer).  ``.mp3`` and ``.wav`` are accepted as
#: fallbacks so contributors can drop in whatever they have.
SUPPORTED_EXTENSIONS: tuple[str, ...] = (".ogg", ".mp3", ".wav", ".flac")

#: Default volume (0.0 - 1.0) applied on init.  Individual ``play()``
#: calls can override per-track.
DEFAULT_MUSIC_VOLUME: float = 0.55

#: Default crossfade duration in milliseconds when switching tracks.
DEFAULT_FADE_MS: int = 800


class MusicManager:
    """Thin wrapper over ``pygame.mixer.music``.

    All methods are safe to call before the mixer is initialized and
    before any audio files exist on disk; they degrade to no-ops with a
    debug log line.  The first call to ``play()`` (or ``init()``)
    attempts to bring the mixer up.
    """

    def __init__(
        self,
        music_dir: Path = MUSIC_DIR,
        *,
        volume: float = DEFAULT_MUSIC_VOLUME,
    ) -> None:
        self.music_dir = music_dir
        self._volume = max(0.0, min(1.0, volume))
        self._initialized: bool = False
        self._init_failed: bool = False
        self._current_track: str | None = None
        self._paused: bool = False
        # Playlist state (only populated when the active track id
        # resolved to a directory of audio files).
        self._playlist: list[Path] = []
        self._playlist_index: int = 0
        self._playlist_fade_ms: int = DEFAULT_FADE_MS

    # ── Lifecycle ────────────────────────────────────────────────

    def init(self) -> bool:
        """Bring the mixer up.  Returns True if music can be played.

        Safe to call repeatedly.  Returns False (without retrying) on
        subsequent calls if the first attempt failed.
        """
        if self._initialized:
            return True
        if self._init_failed:
            return False
        try:
            if not pygame.mixer.get_init():
                # Sensible defaults: 44.1 kHz stereo, small buffer for
                # responsive scene-change crossfades.
                pygame.mixer.init(
                    frequency=44100, size=-16, channels=2, buffer=512,
                )
            pygame.mixer.music.set_volume(self._volume)
            self._initialized = True
            return True
        except pygame.error as exc:
            log.info("Music disabled — mixer init failed: %s", exc)
            self._init_failed = True
            return False

    def shutdown(self) -> None:
        """Stop music and tear down the mixer (called on game exit)."""
        if not self._initialized:
            return
        try:
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()
        except pygame.error:
            pass
        self._current_track = None
        self._paused = False

    # ── Track resolution ─────────────────────────────────────────

    def resolve(self, track_id: str) -> Path | None:
        """Return the first existing file for ``track_id`` or None."""
        for ext in SUPPORTED_EXTENSIONS:
            candidate = self.music_dir / f"{track_id}{ext}"
            if candidate.exists():
                return candidate
        return None

    def resolve_playlist(self, track_id: str) -> list[Path]:
        """Return a sorted list of audio files in ``<music_dir>/<id>/``.

        Returns an empty list if the directory does not exist or holds
        no files with a supported extension.
        """
        folder = self.music_dir / track_id
        if not folder.is_dir():
            return []
        files = [
            p for p in folder.iterdir()
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
        ]
        files.sort(key=lambda p: p.name.lower())
        return files

    # ── Playback control ─────────────────────────────────────────

    def play(
        self,
        track_id: str,
        *,
        loops: int = -1,
        fade_ms: int = DEFAULT_FADE_MS,
        volume: float | None = None,
    ) -> None:
        """Crossfade into ``track_id`` and loop it.

        If ``track_id`` is already playing, this is a no-op (so it is
        safe to call from per-frame state checks).
        """
        if track_id == self._current_track and not self._paused:
            return
        if not self.init():
            return

        # Prefer a folder playlist over a single file with the same id.
        playlist = self.resolve_playlist(track_id)
        if playlist:
            self._fade_out_current(fade_ms)
            self._playlist = playlist
            self._playlist_index = 0
            self._playlist_fade_ms = fade_ms
            self._current_track = track_id
            self._paused = False
            self._play_playlist_entry(
                fade_ms=fade_ms, volume=volume,
            )
            return

        path = self.resolve(track_id)
        if path is None:
            log.debug("No audio file for music track '%s' under %s",
                      track_id, self.music_dir)
            # Still update bookkeeping so the next call to a different
            # missing track also no-ops, and switching back to a real
            # file later can recover.
            self._fade_out_current(fade_ms)
            self._playlist = []
            self._current_track = None
            return

        try:
            self._fade_out_current(fade_ms)
            self._playlist = []
            pygame.mixer.music.load(str(path))
            target_vol = self._volume if volume is None else max(0.0, min(1.0, volume))
            pygame.mixer.music.set_volume(target_vol)
            pygame.mixer.music.play(loops=loops, fade_ms=fade_ms)
            self._current_track = track_id
            self._paused = False
        except pygame.error as exc:
            log.warning("Failed to play music track '%s' (%s): %s",
                        track_id, path, exc)
            self._current_track = None

    def stop(self, *, fade_ms: int = DEFAULT_FADE_MS) -> None:
        if not self._initialized:
            return
        self._fade_out_current(fade_ms)
        self._playlist = []
        self._current_track = None
        self._paused = False

    def tick(self) -> None:
        """Advance the active playlist when the current entry ends.

        Cheap to call every frame; no-op when no playlist is active,
        the mixer is down, music is paused, or the current entry is
        still playing.
        """
        if (
            not self._initialized
            or not self._playlist
            or self._paused
        ):
            return
        try:
            busy = pygame.mixer.music.get_busy()
        except pygame.error:
            return
        if busy:
            return
        # Current entry finished — advance (wrapping) and play next.
        self._playlist_index = (self._playlist_index + 1) % len(self._playlist)
        # No fade between playlist entries — they should feel like one
        # continuous soundtrack, not separate songs being swapped in.
        self._play_playlist_entry(fade_ms=0, volume=None)

    def pause(self) -> None:
        if not self._initialized or self._current_track is None:
            return
        try:
            pygame.mixer.music.pause()
            self._paused = True
        except pygame.error:
            pass

    def resume(self) -> None:
        if not self._initialized or not self._paused:
            return
        try:
            pygame.mixer.music.unpause()
            self._paused = False
        except pygame.error:
            pass

    def set_volume(self, volume: float) -> None:
        """Set the master music volume (0.0 - 1.0)."""
        self._volume = max(0.0, min(1.0, volume))
        if self._initialized:
            try:
                pygame.mixer.music.set_volume(self._volume)
            except pygame.error:
                pass

    # ── Introspection ────────────────────────────────────────────

    @property
    def current_track(self) -> str | None:
        return self._current_track

    @property
    def volume(self) -> float:
        return self._volume

    @property
    def is_paused(self) -> bool:
        return self._paused

    # ── Internals ────────────────────────────────────────────────

    def _fade_out_current(self, fade_ms: int) -> None:
        if self._current_track is None:
            return
        try:
            if fade_ms > 0:
                pygame.mixer.music.fadeout(fade_ms)
            else:
                pygame.mixer.music.stop()
        except pygame.error:
            pass

    def _play_playlist_entry(
        self, *, fade_ms: int, volume: float | None,
    ) -> None:
        """Load and play the playlist entry at ``self._playlist_index``."""
        if not self._playlist:
            return
        path = self._playlist[self._playlist_index]
        try:
            pygame.mixer.music.load(str(path))
            target_vol = (
                self._volume if volume is None
                else max(0.0, min(1.0, volume))
            )
            pygame.mixer.music.set_volume(target_vol)
            # loops=0 → play this entry once; tick() advances to the
            # next entry (wrapping) when the mixer reports idle.
            pygame.mixer.music.play(loops=0, fade_ms=fade_ms)
        except pygame.error as exc:
            log.warning("Failed to play playlist entry '%s': %s", path, exc)
            # Drop the bad entry so we don't loop forever on it.
            del self._playlist[self._playlist_index]
            if self._playlist:
                self._playlist_index %= len(self._playlist)
            else:
                self._current_track = None


# Singleton — import as ``from compprog_pygame.audio import music``.
music = MusicManager()


__all__ = [
    "DEFAULT_FADE_MS",
    "DEFAULT_MUSIC_VOLUME",
    "MUSIC_DIR",
    "MusicManager",
    "SUPPORTED_EXTENSIONS",
    "music",
]
