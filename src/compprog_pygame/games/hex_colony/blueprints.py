"""Blueprint system for Hex Colony.

A blueprint captures the relative layout of multiple buildings so the
player can stamp repeatable patterns.  Blueprints are stored as lists
of (offset, building_type) pairs relative to an anchor point.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from compprog_pygame.games.hex_colony.buildings import BuildingType
from compprog_pygame.games.hex_colony.hex_grid import HexCoord


@dataclass
class BlueprintEntry:
    """A single building in a blueprint, stored as an offset from anchor."""
    dq: int
    dr: int
    building_type: BuildingType


@dataclass
class Blueprint:
    """A saved multi-building layout."""
    name: str
    entries: list[BlueprintEntry] = field(default_factory=list)

    def shifted(self, anchor: HexCoord) -> list[tuple[HexCoord, BuildingType]]:
        """Return absolute coordinates when placed at *anchor*."""
        return [
            (HexCoord(anchor.q + e.dq, anchor.r + e.dr), e.building_type)
            for e in self.entries
        ]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "entries": [
                {"dq": e.dq, "dr": e.dr, "type": e.building_type.name}
                for e in self.entries
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> Blueprint:
        entries = [
            BlueprintEntry(
                dq=e["dq"], dr=e["dr"],
                building_type=BuildingType[e["type"]],
            )
            for e in data.get("entries", [])
        ]
        return cls(name=data.get("name", "Unnamed"), entries=entries)


class BlueprintManager:
    """Manages creation, storage, and recall of blueprints."""

    MAX_BLUEPRINTS = 10

    def __init__(self) -> None:
        self.blueprints: list[Blueprint] = []
        self._recording: bool = False
        self._record_anchor: HexCoord | None = None
        self._record_entries: list[BlueprintEntry] = []

    # ── Recording ────────────────────────────────────────────────

    def start_recording(self, anchor: HexCoord) -> None:
        """Begin recording a new blueprint from the given anchor hex."""
        self._recording = True
        self._record_anchor = anchor
        self._record_entries = []

    def record_building(self, coord: HexCoord, btype: BuildingType) -> None:
        """Record a building placement during recording."""
        if not self._recording or self._record_anchor is None:
            return
        dq = coord.q - self._record_anchor.q
        dr = coord.r - self._record_anchor.r
        self._record_entries.append(BlueprintEntry(dq=dq, dr=dr, building_type=btype))

    def finish_recording(self, name: str) -> Blueprint | None:
        """Finish recording and save the blueprint."""
        if not self._recording or not self._record_entries:
            self._recording = False
            return None
        bp = Blueprint(name=name, entries=list(self._record_entries))
        self.blueprints.append(bp)
        if len(self.blueprints) > self.MAX_BLUEPRINTS:
            self.blueprints.pop(0)
        self._recording = False
        self._record_entries = []
        self._record_anchor = None
        return bp

    def cancel_recording(self) -> None:
        self._recording = False
        self._record_entries = []
        self._record_anchor = None

    @property
    def is_recording(self) -> bool:
        return self._recording

    # ── Persistence ──────────────────────────────────────────────

    def save_to_file(self, path: Path) -> None:
        data = [bp.to_dict() for bp in self.blueprints]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2))

    def load_from_file(self, path: Path) -> None:
        if not path.exists():
            return
        data = json.loads(path.read_text())
        self.blueprints = [Blueprint.from_dict(d) for d in data]
