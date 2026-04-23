# Background music

Drop audio files in this folder named after a *logical track id*:

| File | Plays during |
|---|---|
| `menu.ogg` (or `.mp3` / `.wav` / `.flac`) | The home screen and the Hex Colony seed-select menu |
| `cutscene.ogg` | The intro cutscene and the awakening / rocket-launch cutscenes |
| `gameplay.ogg` | In-game (after the cutscene finishes) |

## Playlists (multiple tracks per id)

If a *folder* exists here named after a track id, it is treated as a
playlist: every supported audio file inside is played in sorted
filename order, and the playlist loops back to the first track when the
last one ends.  A folder takes precedence over a single file with the
same name.

Recommended layout for gameplay music:

```
assets/audio/music/
    menu.ogg
    cutscene.ogg
    gameplay/
        01_dawn.ogg
        02_industry.ogg
        03_night.ogg
```

Order is by filename (case-insensitive) — prefix with `01_`, `02_`, …
to control sequence.  Mix and match extensions freely.

Add new tracks by:

1. Picking a new logical id (e.g. `victory`).
2. Saving `victory.ogg` here.
3. Calling `music.play("victory")` from wherever you want it to start —
   see [`src/compprog_pygame/audio.py`](../../../src/compprog_pygame/audio.py).

Format notes:

* `.ogg` (Vorbis) is preferred — it loops seamlessly and is small.
* `.mp3` works but tends to introduce a tiny gap on loop.
* Volume can be set globally with `music.set_volume(0.0 .. 1.0)` or
  per-track via the `volume=` argument to `music.play()`.

If a file is missing the framework no-ops gracefully, so it's safe to
ship the game without any music files — the calls are already wired in.
