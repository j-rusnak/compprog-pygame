"""Rival AI colony — "The Other Colony" enemy.

A re-evolved Earth has more than one tribe of survivors. This module
introduces a single, fully-simulated rival faction that:

* Spawns at one of the AI camp coordinates picked by procgen.
* Owns its own :class:`ColonyState` (inventory, tech tree, tier).
* Builds visible primitive ``HOUSE`` tiles around its ``TRIBAL_CAMP``
  on a slow timer, expanding from the camp like a real colony.
* Advances tiers and researches tech on an abstracted economy whose
  rate scales with tier and with the player's relations.
* Maintains a diplomacy state (Hostile / Tense / Neutral / Friendly /
  Allied) with the player and acts on it:

  * **Hostile** — periodically launches raids that steal resources
    from a random reachable player building and may briefly disable
    it (``active=False``).
  * **Friendly / Allied** — periodically sends gifts of resources to
    the player's inventory.

* Races the player to the rocket: once the rival reaches its launch
  tier, a slow ``rocket_progress`` bar starts filling.  If it
  completes before the player launches, the run ends in a loss with
  a "they reached space first" message.

Player → rival actions live on :class:`RivalColony` (``send_gift``,
``propose_trade``, ``declare_war``, ``sue_for_peace``) and are wired
into the :class:`~compprog_pygame.games.hex_colony.ui_rival_colony.RivalColonyOverlay`
panel.

The simulation here is intentionally *abstracted* — the rival does
not run worker / hauler / station logic the way the player's
:class:`~compprog_pygame.games.hex_colony.world.World` does.  Doing
that would double the simulation cost and require six big station
tuples to track every change.  Instead, the rival has a simple
"production budget" that translates into placed buildings, advanced
tech, and increasing power over time.  Every player-visible effect
(buildings on the map, tier badges, raid notifications) is real.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from compprog_pygame.games.hex_colony.buildings import BuildingType
from compprog_pygame.games.hex_colony.colony import ColonyState
from compprog_pygame.games.hex_colony.hex_grid import HexCoord
from compprog_pygame.games.hex_colony.resources import Resource
from compprog_pygame.games.hex_colony import params
from compprog_pygame.games.hex_colony import strings as S

if TYPE_CHECKING:
    from compprog_pygame.games.hex_colony.notifications import (
        NotificationManager,
    )
    from compprog_pygame.games.hex_colony.world import World


# ── Diplomacy ──────────────────────────────────────────────────

class DiplomacyState(Enum):
    """Discrete relationship buckets derived from ``RivalColony.relation``."""
    HOSTILE = "hostile"
    TENSE = "tense"
    NEUTRAL = "neutral"
    FRIENDLY = "friendly"
    ALLIED = "allied"


# Relation thresholds (inclusive lower bounds).  Tuned so the default
# starting relation of 0 sits squarely in NEUTRAL with a buffer either
# side that's wide enough to trade or skirmish without immediately
# tipping into the next bucket.
_STATE_THRESHOLDS: list[tuple[int, DiplomacyState]] = [
    (60,  DiplomacyState.ALLIED),
    (25,  DiplomacyState.FRIENDLY),
    (-25, DiplomacyState.NEUTRAL),
    (-60, DiplomacyState.TENSE),
    (-101, DiplomacyState.HOSTILE),
]


def _state_for_relation(relation: float) -> DiplomacyState:
    for thresh, state in _STATE_THRESHOLDS:
        if relation >= thresh:
            return state
    return DiplomacyState.HOSTILE


# Cosmetic colour used by the overlay to tint the diplomacy badge.
DIPLOMACY_COLORS: dict[DiplomacyState, tuple[int, int, int]] = {
    DiplomacyState.HOSTILE:  (210, 70, 70),
    DiplomacyState.TENSE:    (220, 140, 70),
    DiplomacyState.NEUTRAL:  (190, 190, 200),
    DiplomacyState.FRIENDLY: (130, 200, 110),
    DiplomacyState.ALLIED:   (90, 180, 230),
}


# Names sampled deterministically from the world seed so the same seed
# always spawns the same rival.  Flavoured for the "re-evolved Earth"
# theme.
_RIVAL_NAMES: tuple[str, ...] = (
    "The Verdant Compact",
    "The Ironroot Hold",
    "The Ash Conclave",
    "The Salt Coalition",
    "The Vine Choir",
    "The Stoneweavers",
    "The Tide Pact",
    "The Ember Court",
)


# ── Trade offers ───────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class TradeOffer:
    """A single pre-defined exchange the rival is willing to make.

    The player gives ``give`` and receives ``get``.  The rival accepts
    iff their stockpile has enough of ``get_res`` AND the current
    diplomacy state is NEUTRAL or better.  Successful trades grant a
    small relation bonus.
    """
    give_res: Resource
    give_amt: int
    get_res: Resource
    get_amt: int
    relation_bonus: int = 3


# Static catalogue of trade offers shown in the diplomacy panel.
# Choices favour resources the rival is plausibly producing
# (raw → processed swaps) so the player has a reason to engage even
# late in the game.
DEFAULT_TRADES: tuple[TradeOffer, ...] = (
    TradeOffer(Resource.WOOD,    50, Resource.STONE,      30),
    TradeOffer(Resource.STONE,   50, Resource.WOOD,       30),
    TradeOffer(Resource.FOOD,    40, Resource.FIBER,      30),
    TradeOffer(Resource.FOOD,    80, Resource.IRON,       20),
    TradeOffer(Resource.WOOD,   100, Resource.COPPER,     20),
    TradeOffer(Resource.IRON,    20, Resource.IRON_BAR,   10, relation_bonus=4),
    TradeOffer(Resource.COPPER,  20, Resource.COPPER_BAR, 10, relation_bonus=4),
)


# Resources the player is allowed to gift.  Limited to bulk raw
# materials so the dialog stays compact; advanced materials would
# clutter the panel without adding strategic depth.
GIFT_RESOURCES: tuple[Resource, ...] = (
    Resource.WOOD, Resource.STONE, Resource.FOOD,
    Resource.FIBER, Resource.IRON, Resource.COPPER,
)
GIFT_AMOUNTS: tuple[int, ...] = (10, 50, 100)


# ── Rival colony ───────────────────────────────────────────────

# Tier index at which the rival begins assembling their rocket.  Match
# the player's late-game tier so the race feels fair.
RIVAL_LAUNCH_TIER: int = params.RIVAL_LAUNCH_TIER

# Real-time seconds (at 1x speed) the rival needs to advance one tier
# at the start of the game.  Each subsequent tier scales by
# RIVAL_TIER_TIME_SCALE so the late game is slower.
_TIER_TIME_BASE: float = params.RIVAL_TIER_TIME_BASE
_TIER_TIME_SCALE: float = params.RIVAL_TIER_TIME_SCALE

# Real-time seconds the rival needs to fully assemble + launch the
# rocket once they reach RIVAL_LAUNCH_TIER.  The bar is shown to the
# player once it starts ticking so they can see the threat.
_ROCKET_TIME: float = params.RIVAL_ROCKET_TIME

# Real-time seconds between hostile raid attempts.
_RAID_INTERVAL: float = params.RIVAL_RAID_INTERVAL

# Real-time seconds between friendly gift drops.
_GIFT_INTERVAL: float = params.RIVAL_GIFT_INTERVAL

# (Building expansion is purely visual now: the rival is rendered as a
# single hex sprite whose radius grows by one hex per tier.  See
# ``render_buildings.draw_rival_camp``.  No HOUSE placements are made,
# so the rival never collides with player infrastructure.)


@dataclass
class _LogEntry:
    """One line in the rival's recent-events log shown in the UI."""
    time: float
    text: str
    color: tuple[int, int, int] = (220, 220, 230)


@dataclass
class RivalColony:
    """One AI rival faction sharing the world with the player.

    All time inputs are *simulation* seconds (already scaled by the
    player's selected sim speed) so the rival and player progress in
    lockstep when the player presses 5x speed.
    """
    faction_id: str
    name: str
    camp_coord: HexCoord
    colony: ColonyState

    # Diplomatic relation in [-100, 100].  Starts at 0 (NEUTRAL).
    relation: float = 0.0
    # Whether the player has formally declared war.  Locks the state
    # to HOSTILE until peace is sued for, regardless of relation.
    war_declared: bool = False

    # Rival progression — abstract tier/tech timers (real-time).
    tier_progress: float = 0.0
    rocket_progress: float = 0.0
    rocket_started: bool = False
    launched: bool = False

    # Internal action timers.
    _raid_accum: float = 0.0
    _gift_accum: float = 0.0
    _relation_drift_accum: float = 0.0

    # Disable durations applied to player buildings by sabotage raids.
    # Maps id(building) → seconds remaining.  Buildings expire and
    # become active again automatically.
    _disabled_buildings: dict[int, float] = field(default_factory=dict)

    # Rolling event log shown in the diplomacy panel.
    log: list[_LogEntry] = field(default_factory=list)

    # Deterministic RNG seeded from the world seed + faction id.  All
    # rival randomness flows through this so reloads of the same seed
    # produce the same raid targets, gift contents, etc.
    rng: random.Random = field(default_factory=random.Random)

    # ── Construction helpers ─────────────────────────────────────

    @classmethod
    def create(
        cls, *, faction_id: str, name: str, camp_coord: HexCoord,
        seed: str,
    ) -> "RivalColony":
        rng = random.Random(f"{seed}::{faction_id}")
        colony = ColonyState(
            faction_id=faction_id,
            camp_coord=camp_coord,
            is_player=False,
        )
        # Bootstrap the rival with a small starting stockpile so its
        # gift / trade offers aren't immediately starved.
        for r, amt in params.RIVAL_START_RESOURCES.items():
            colony.inventory.add(Resource[r], amt)
        return cls(
            faction_id=faction_id,
            name=name,
            camp_coord=camp_coord,
            colony=colony,
            rng=rng,
        )

    # ── Derived properties ───────────────────────────────────────

    @property
    def state(self) -> DiplomacyState:
        if self.war_declared:
            return DiplomacyState.HOSTILE
        return _state_for_relation(self.relation)

    @property
    def tier(self) -> int:
        return self.colony.tier_tracker.current_tier

    @property
    def building_count(self) -> int:
        # Rival is now a single hex sprite that grows by tier; report a
        # representative footprint (1 hex at tier 0, +1 each tier) for
        # the diplomacy panel summary.
        return self.tier + 1

    @property
    def population(self) -> int:
        # Population scales with the visible footprint so the UI summary
        # still climbs as the rival advances.  Not a real head-count.
        return params.RIVAL_POP_PER_BUILDING * self.building_count

    @property
    def power_rating(self) -> int:
        """1-10 score shown in the UI summarising rival strength."""
        score = self.tier * 1.2 + min(7.0, self.building_count * 0.5)
        if self.rocket_started:
            score += 2.0 + self.rocket_progress * 2.0
        return max(1, min(10, int(score)))

    @property
    def rocket_eta_seconds(self) -> float | None:
        """Real-time seconds until the rival rocket completes, or None
        if it hasn't been started yet."""
        if not self.rocket_started or self.launched:
            return None
        remaining = max(0.0, _ROCKET_TIME - self.rocket_progress)
        return remaining

    # ── Mutators used by the simulation ──────────────────────────

    def _push_log(self, text: str, color: tuple[int, int, int] = (220, 220, 230)) -> None:
        self.log.append(_LogEntry(
            time=self._sim_now, text=text, color=color,
        ))
        # Keep the log bounded so memory and UI scroll stay sane.
        if len(self.log) > params.RIVAL_LOG_LIMIT:
            del self.log[: len(self.log) - params.RIVAL_LOG_LIMIT]

    _sim_now: float = 0.0

    def adjust_relation(self, delta: float) -> None:
        """Clamp ``relation`` to [-100, 100] after applying ``delta``."""
        self.relation = max(-100.0, min(100.0, self.relation + delta))

    # ── Per-frame tick ──────────────────────────────────────────

    def tick(
        self, world: "World", dt: float,
        notifications: "NotificationManager | None" = None,
    ) -> None:
        """Advance the rival simulation by *dt* simulation-seconds.

        Called from :meth:`World.update` after the player's own tick
        so all building placements / removals this frame are visible.
        """
        if self.launched:
            return
        self._sim_now = world.time_elapsed

        # ── Tier / tech progression ──────────────────────────
        # The rival's visible footprint is purely a function of tier;
        # advancing a tier automatically grows the sprite by one hex
        # radius (handled in the renderer).  No buildings are placed.
        self._advance_tiers(dt, notifications)

        # ── Diplomacy actions ────────────────────────────────
        state = self.state
        if state == DiplomacyState.HOSTILE:
            self._raid_accum += dt
            if self._raid_accum >= _RAID_INTERVAL:
                self._raid_accum = 0.0
                self._do_raid(world, notifications)
        else:
            # Hostility cooldown decays slowly when not at war.
            self._raid_accum = max(0.0, self._raid_accum - dt * 0.5)

        if state in (DiplomacyState.FRIENDLY, DiplomacyState.ALLIED):
            self._gift_accum += dt
            if self._gift_accum >= _GIFT_INTERVAL:
                self._gift_accum = 0.0
                self._send_gift_to_player(world, notifications)
        else:
            self._gift_accum = 0.0

        # ── Relation drift toward 0 (peace is the stable state)
        # but stops drifting once a war is formally declared.
        if not self.war_declared:
            self._relation_drift_accum += dt
            if self._relation_drift_accum >= 5.0:
                self._relation_drift_accum = 0.0
                if self.relation > 0:
                    self.relation = max(0.0, self.relation - 1.0)
                elif self.relation < 0:
                    self.relation = min(0.0, self.relation + 1.0)

        # ── Disable timers ───────────────────────────────────
        if self._disabled_buildings:
            expired = []
            for bid, remaining in self._disabled_buildings.items():
                remaining -= dt
                if remaining <= 0:
                    expired.append(bid)
                else:
                    self._disabled_buildings[bid] = remaining
            for bid in expired:
                del self._disabled_buildings[bid]
                # Re-enable the building if it's still around.
                for b in world.buildings.buildings:
                    if id(b) == bid:
                        b.active = True
                        break

    # ── Tier / tech progression ────────────────────────────────

    def _advance_tiers(
        self, dt: float, notifications: "NotificationManager | None",
    ) -> None:
        from compprog_pygame.games.hex_colony.tech_tree import TIERS
        tier = self.colony.tier_tracker.current_tier
        if tier >= len(TIERS) - 1:
            # Already at max tier — feed the rocket instead.
            if not self.rocket_started:
                self.rocket_started = True
                self._push_log(
                    S.RIVAL_LOG_ROCKET_START.format(name=self.name),
                    (240, 200, 80),
                )
                if notifications is not None:
                    notifications.push(
                        S.NOTIF_RIVAL_ROCKET_START.format(name=self.name),
                        (240, 200, 80),
                    )
            self.rocket_progress += dt
            if self.rocket_progress >= _ROCKET_TIME:
                self.launched = True
                self._push_log(
                    S.RIVAL_LOG_LAUNCHED.format(name=self.name),
                    (240, 100, 100),
                )
                if notifications is not None:
                    notifications.push(
                        S.NOTIF_RIVAL_LAUNCHED.format(name=self.name),
                        (240, 100, 100),
                    )
            return

        # Friendly relations slow the rival; hostile relations speed
        # them up (because both sides are arming).  Multiplier in
        # roughly [0.7, 1.4].
        rel_mult = 1.0
        if self.relation >= 60:
            rel_mult = 0.7
        elif self.relation >= 25:
            rel_mult = 0.85
        elif self.relation <= -60:
            rel_mult = 1.4
        elif self.relation <= -25:
            rel_mult = 1.15

        # Each tier takes longer than the last so the player has time
        # to react in the mid-late game.
        tier_time = _TIER_TIME_BASE * (_TIER_TIME_SCALE ** tier)
        self.tier_progress += dt / max(1.0, tier_time) / rel_mult

        if self.tier_progress >= 1.0:
            self.tier_progress = 0.0
            self.colony.tier_tracker.current_tier = min(
                tier + 1, len(TIERS) - 1,
            )
            new_tier = TIERS[self.colony.tier_tracker.current_tier]
            self._push_log(
                S.RIVAL_LOG_TIER.format(
                    name=self.name, tier=new_tier.name,
                ),
                (200, 220, 240),
            )
            if notifications is not None:
                notifications.push(
                    S.NOTIF_RIVAL_TIER.format(
                        name=self.name, tier=new_tier.name,
                    ),
                    (200, 220, 240),
                )

    # ── Hostile actions ────────────────────────────────────────

    def _do_raid(
        self, world: "World",
        notifications: "NotificationManager | None",
    ) -> None:
        """Pick a random player building and either steal resources
        from its on-site storage or briefly disable it.  No-ops
        cleanly if the player has no eligible buildings."""
        targets = [
            b for b in world.buildings.buildings
            if getattr(b, "faction", "SURVIVOR") == "SURVIVOR"
            and b.type not in (BuildingType.PATH, BuildingType.BRIDGE,
                               BuildingType.CONVEYOR, BuildingType.WALL,
                               BuildingType.PIPE, BuildingType.CAMP)
        ]
        if not targets:
            return
        target = self.rng.choice(targets)

        # Roll for raid type: 70% theft, 30% sabotage.
        if self.rng.random() < 0.3:
            # Sabotage: disable the building for a fixed duration.
            target.active = False
            self._disabled_buildings[id(target)] = params.RIVAL_RAID_DISABLE_TIME
            label = S.building_label(target.type.name)
            msg = S.NOTIF_RIVAL_SABOTAGE.format(
                name=self.name, building=label,
            )
            self._push_log(
                S.RIVAL_LOG_SABOTAGE.format(building=label),
                (240, 120, 90),
            )
            if notifications is not None:
                notifications.push(msg, (240, 120, 90))
            return

        # Theft: steal up to RIVAL_RAID_STEAL_FRACTION of one resource
        # type held by the building.  We also pull from the player's
        # global inventory if the building's local stash is empty.
        stolen_res: Resource | None = None
        stolen_amt: float = 0.0
        if target.storage:
            non_zero = [
                (res, amt) for res, amt in target.storage.items()
                if amt > 0.5
            ]
            if non_zero:
                res, amt = self.rng.choice(non_zero)
                steal = max(
                    1.0, amt * params.RIVAL_RAID_STEAL_FRACTION,
                )
                steal = min(steal, amt)
                target.storage[res] -= steal
                self.colony.inventory.add(res, steal)
                stolen_res, stolen_amt = res, steal
        if stolen_res is None:
            # Building was empty — pull a small amount from the
            # player's global inventory instead.
            inv = world.player_colony.inventory
            options = [
                r for r in (Resource.WOOD, Resource.FOOD, Resource.STONE,
                            Resource.IRON, Resource.COPPER, Resource.FIBER)
                if inv[r] >= 5
            ]
            if options:
                res = self.rng.choice(options)
                steal = min(inv[res], 25.0)
                inv[res] = inv[res] - steal
                self.colony.inventory.add(res, steal)
                stolen_res, stolen_amt = res, steal
        if stolen_res is None:
            # Nothing worth stealing — log a near-miss and move on.
            self._push_log(
                S.RIVAL_LOG_RAID_FAIL, (200, 200, 110),
            )
            if notifications is not None:
                notifications.push(
                    S.NOTIF_RIVAL_RAID_FAIL.format(name=self.name),
                    (200, 200, 110),
                )
            return

        label = S.building_label(target.type.name)
        res_name = S.resource_name(stolen_res.name)
        msg = S.NOTIF_RIVAL_RAID.format(
            name=self.name, amount=int(stolen_amt),
            resource=res_name, building=label,
        )
        self._push_log(
            S.RIVAL_LOG_RAID.format(
                amount=int(stolen_amt), resource=res_name,
                building=label,
            ),
            (240, 120, 90),
        )
        if notifications is not None:
            notifications.push(msg, (240, 120, 90))

    # ── Friendly actions ────────────────────────────────────────

    def _send_gift_to_player(
        self, world: "World",
        notifications: "NotificationManager | None",
    ) -> None:
        """Push a small bundle of resources into the player's inventory
        once the relation is FRIENDLY+.  Pulls from the rival's own
        stockpile so the gesture isn't free."""
        # Pick a resource the rival has plenty of.
        candidates = [
            r for r in GIFT_RESOURCES
            if self.colony.inventory[r] >= 30
        ]
        if not candidates:
            return
        res = self.rng.choice(candidates)
        amount = self.rng.choice((10, 20, 30))
        amount = min(amount, int(self.colony.inventory[res]))
        if amount <= 0:
            return
        self.colony.inventory[res] = self.colony.inventory[res] - amount
        world.player_colony.inventory.add(res, amount)
        msg = S.NOTIF_RIVAL_GIFT.format(
            name=self.name, amount=amount,
            resource=S.resource_name(res.name),
        )
        self._push_log(
            S.RIVAL_LOG_GIFT.format(
                amount=amount, resource=S.resource_name(res.name),
            ),
            (140, 220, 140),
        )
        if notifications is not None:
            notifications.push(msg, (140, 220, 140))

    # ── Player-driven actions (called from the UI) ───────────────

    def send_gift(
        self, world: "World", res: Resource, amount: int,
        notifications: "NotificationManager | None" = None,
    ) -> bool:
        """Player → rival gift.  Debits the player's inventory, credits
        the rival's, and bumps relation.  Returns True on success."""
        inv = world.player_colony.inventory
        if inv[res] < amount or amount <= 0:
            return False
        inv[res] = inv[res] - amount
        self.colony.inventory.add(res, amount)
        # Bigger gifts move the needle more, but with diminishing
        # returns so a single 100-unit drop doesn't max out relation.
        delta = min(20, max(1, int(amount / 10)))
        # Bonus for gifting scarce / valuable resources.
        if res in (Resource.IRON, Resource.COPPER):
            delta += 3
        self.adjust_relation(delta)
        # Receiving a gift also reduces accumulated raid pressure.
        self._raid_accum = 0.0
        self._push_log(
            S.RIVAL_LOG_PLAYER_GIFT.format(
                amount=amount, resource=S.resource_name(res.name),
            ),
            (140, 220, 140),
        )
        if notifications is not None:
            notifications.push(
                S.NOTIF_PLAYER_GIFT.format(
                    name=self.name, amount=amount,
                    resource=S.resource_name(res.name),
                ),
                (140, 220, 140),
            )
        return True

    def propose_trade(
        self, world: "World", offer: TradeOffer,
        notifications: "NotificationManager | None" = None,
    ) -> bool:
        """Attempt the trade.  Rival accepts iff its stockpile of
        ``offer.get_res`` covers the request AND state is at least
        TENSE (open hostilities forbid trade)."""
        if self.state == DiplomacyState.HOSTILE:
            if notifications is not None:
                notifications.push(
                    S.NOTIF_TRADE_REJECTED_WAR.format(name=self.name),
                    (220, 100, 100),
                )
            return False
        inv = world.player_colony.inventory
        rival_inv = self.colony.inventory
        if inv[offer.give_res] < offer.give_amt:
            if notifications is not None:
                notifications.push(
                    S.NOTIF_TRADE_PLAYER_SHORT, (220, 180, 70),
                )
            return False
        if rival_inv[offer.get_res] < offer.get_amt:
            if notifications is not None:
                notifications.push(
                    S.NOTIF_TRADE_REJECTED_STOCK.format(name=self.name),
                    (220, 180, 70),
                )
            return False
        # Execute.
        inv[offer.give_res] = inv[offer.give_res] - offer.give_amt
        inv.add(offer.get_res, offer.get_amt)
        rival_inv.add(offer.give_res, offer.give_amt)
        rival_inv[offer.get_res] = rival_inv[offer.get_res] - offer.get_amt
        self.adjust_relation(offer.relation_bonus)
        give_n = S.resource_name(offer.give_res.name)
        get_n = S.resource_name(offer.get_res.name)
        self._push_log(
            S.RIVAL_LOG_TRADE.format(
                give_amt=offer.give_amt, give=give_n,
                get_amt=offer.get_amt, get=get_n,
            ),
            (180, 220, 230),
        )
        if notifications is not None:
            notifications.push(
                S.NOTIF_TRADE_OK.format(name=self.name),
                (180, 220, 230),
            )
        return True

    def declare_war(
        self,
        notifications: "NotificationManager | None" = None,
    ) -> None:
        """Player declares war.  Locks state to HOSTILE and zeroes the
        next-raid timer so consequences are immediate."""
        if self.war_declared:
            return
        self.war_declared = True
        self.relation = -80.0
        self._raid_accum = _RAID_INTERVAL * 0.75  # raid soon
        self._push_log(
            S.RIVAL_LOG_PLAYER_WAR.format(name=self.name),
            (240, 100, 100),
        )
        if notifications is not None:
            notifications.push(
                S.NOTIF_PLAYER_WAR.format(name=self.name),
                (240, 100, 100),
            )

    def sue_for_peace(
        self, world: "World",
        notifications: "NotificationManager | None" = None,
    ) -> bool:
        """Pay the war-end tribute and return to TENSE.  Returns True
        on success.  Tribute amount lives in :mod:`params`."""
        if not self.war_declared:
            return False
        inv = world.player_colony.inventory
        tribute_res = Resource[params.RIVAL_PEACE_TRIBUTE_RESOURCE]
        tribute_amt = params.RIVAL_PEACE_TRIBUTE_AMOUNT
        if inv[tribute_res] < tribute_amt:
            if notifications is not None:
                notifications.push(
                    S.NOTIF_PEACE_REJECTED.format(
                        amount=tribute_amt,
                        resource=S.resource_name(tribute_res.name),
                    ),
                    (220, 180, 70),
                )
            return False
        inv[tribute_res] = inv[tribute_res] - tribute_amt
        self.colony.inventory.add(tribute_res, tribute_amt)
        self.war_declared = False
        self.relation = -50.0
        self._raid_accum = 0.0
        self._push_log(
            S.RIVAL_LOG_PLAYER_PEACE.format(name=self.name),
            (200, 220, 200),
        )
        if notifications is not None:
            notifications.push(
                S.NOTIF_PLAYER_PEACE.format(name=self.name),
                (200, 220, 200),
            )
        return True


def name_for_seed(seed: str) -> str:
    """Pick a deterministic rival name from the world seed."""
    rng = random.Random(f"rival_name::{seed}")
    return rng.choice(_RIVAL_NAMES)
