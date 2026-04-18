"""Advanced statistics popup overlay.

Full-screen modal (styled like the tech-tree overlay) that shows
detailed resource graphs, production / consumption rates, population
growth, and lets the player pick which resources to chart and over
what time window.

Opened from the Stats tab's "Advanced Statistics" button.
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

import pygame

from compprog_pygame.games.hex_colony.resources import (
    PROCESSED_RESOURCES,
    RAW_RESOURCES,
    Resource,
)
from compprog_pygame.games.hex_colony.resource_icons import get_resource_icon
from compprog_pygame.games.hex_colony.tech_tree import is_resource_available
from compprog_pygame.games.hex_colony.ui import (
    Fonts,
    Panel,
    RESOURCE_COLORS,
    UI_ACCENT,
    UI_BG,
    UI_BORDER,
    UI_MUTED,
    UI_OK,
    UI_OVERLAY,
    UI_TEXT,
    draw_button,
    draw_titled_panel,
    render_text_clipped,
)

if TYPE_CHECKING:
    from compprog_pygame.games.hex_colony.tech_tree import TechTree, TierTracker
    from compprog_pygame.games.hex_colony.world import World


# ── Data buffer ──────────────────────────────────────────────────

# History length in samples.  Samples are taken once per second, so
# 600 samples covers 10 minutes — enough headroom for the longest
# time window we offer.
HISTORY_LEN: int = 600
SAMPLE_INTERVAL: float = 1.0


class StatsHistory:
    """Rolling per-resource history shared by the stats tab and popup."""

    def __init__(self) -> None:
        self._history: dict[Resource, deque[float]] = {
            r: deque(maxlen=HISTORY_LEN) for r in Resource
        }
        self._population: deque[float] = deque(maxlen=HISTORY_LEN)
        self._last_sample: float = -1.0

    def sample(self, world: "World") -> None:
        if world.time_elapsed - self._last_sample < SAMPLE_INTERVAL:
            return
        for res in Resource:
            self._history[res].append(float(world.inventory[res]))
        self._population.append(float(world.population.count))
        self._last_sample = world.time_elapsed

    def resource(self, res: Resource) -> deque[float]:
        return self._history[res]

    def population(self) -> deque[float]:
        return self._population

    def rate(self, res: Resource, window_s: int) -> float:
        """Average units/sec *net stockpile change* over the last
        ``window_s`` samples (production minus consumption / hauls).

        This is a coarse signal — for the actual current production
        rate, use :meth:`production_rate` which queries live buildings.
        """
        data = self._history[res]
        if len(data) < 2:
            return 0.0
        n = min(len(data), max(2, window_s))
        recent = list(data)[-n:]
        delta = recent[-1] - recent[0]
        return delta / max(1, (n - 1) * SAMPLE_INTERVAL)

    def production_rate(self, world: "World", res: Resource) -> float:
        """Live units/sec produced by all currently-working production
        buildings for *res*.  Counts only buildings whose ``active``
        flag is set this tick (so stalled producers contribute 0).

        Crafting stations contribute ``output_amount / time * workers``
        when their recipe outputs *res*; gatherers/farms/refineries
        contribute their per-worker rate × workers (× any bonus).
        """
        from compprog_pygame.games.hex_colony import params
        from compprog_pygame.games.hex_colony.buildings import BuildingType
        from compprog_pygame.games.hex_colony.hex_grid import Terrain
        from compprog_pygame.games.hex_colony.resources import (
            MATERIAL_RECIPES,
        )

        s = world.settings
        total = 0.0
        for b in world.buildings.buildings:
            if not getattr(b, "active", False) or b.workers <= 0:
                continue
            t = b.type
            # Raw harvesters
            if t == BuildingType.WOODCUTTER and res == Resource.WOOD:
                total += s.gather_wood * b.workers
            elif t == BuildingType.QUARRY and res == Resource.STONE:
                total += s.gather_stone * b.workers
            elif t == BuildingType.GATHERER:
                if b.gatherer_output == Resource.FOOD and res == Resource.FOOD:
                    total += s.gather_food * b.workers
                elif b.gatherer_output == Resource.FIBER and res == Resource.FIBER:
                    total += s.gather_fiber * b.workers
                elif b.gatherer_output is None and res in (
                    Resource.FOOD, Resource.FIBER,
                ):
                    total += (s.gather_fiber + s.gather_food) * 0.25 * b.workers
            elif t == BuildingType.FARM and res == Resource.FOOD:
                bonus = 1.0
                wells = {
                    w.coord for w in world.buildings.by_type(BuildingType.WELL)
                }
                for nb in b.coord.neighbors():
                    if nb in wells:
                        bonus += params.WELL_FARM_BONUS
                        break
                total += params.FARM_FOOD_RATE * b.workers * bonus
            elif t == BuildingType.REFINERY and b.recipe is None:
                # Adjacency-mining mode (no recipe).
                for nb in b.coord.neighbors():
                    tile = world.grid.get(nb)
                    if tile is None or tile.resource_amount <= 0:
                        continue
                    if (tile.terrain == Terrain.IRON_VEIN
                            and res == Resource.IRON):
                        total += params.REFINERY_RATE * b.workers
                        break
                    if (tile.terrain == Terrain.COPPER_VEIN
                            and res == Resource.COPPER):
                        total += params.REFINERY_RATE * b.workers
                        break
            elif t == BuildingType.MINING_MACHINE:
                # Mining machine doesn't use workers, but it's active.
                for nb in b.coord.neighbors():
                    tile = world.grid.get(nb)
                    if tile is None or tile.resource_amount <= 0:
                        continue
                    if (tile.terrain == Terrain.IRON_VEIN
                            and res == Resource.IRON):
                        total += params.MINING_MACHINE_RATE
                        break
                    if (tile.terrain == Terrain.COPPER_VEIN
                            and res == Resource.COPPER):
                        total += params.MINING_MACHINE_RATE
                        break
            elif t in (
                BuildingType.WORKSHOP, BuildingType.FORGE,
                BuildingType.REFINERY, BuildingType.ASSEMBLER,
            ) and isinstance(b.recipe, Resource):
                mrec = MATERIAL_RECIPES.get(b.recipe)
                if mrec is not None and mrec.output == res and mrec.time > 0:
                    total += (mrec.output_amount / mrec.time) * b.workers
        return total

    def consumption_rate(self, world: "World", res: Resource) -> float:
        """Live units/sec *consumed* by currently-working crafting
        stations using *res* as a recipe input."""
        from compprog_pygame.games.hex_colony.buildings import BuildingType
        from compprog_pygame.games.hex_colony.resources import (
            MATERIAL_RECIPES,
        )
        total = 0.0
        for b in world.buildings.buildings:
            if not getattr(b, "active", False) or b.workers <= 0:
                continue
            if b.type not in (
                BuildingType.WORKSHOP, BuildingType.FORGE,
                BuildingType.REFINERY, BuildingType.ASSEMBLER,
            ):
                continue
            if not isinstance(b.recipe, Resource):
                continue
            mrec = MATERIAL_RECIPES.get(b.recipe)
            if mrec is None or mrec.time <= 0:
                continue
            amt = mrec.inputs.get(res)
            if amt:
                total += (amt / mrec.time) * b.workers
        return total


# ── Time windows offered in the UI ───────────────────────────────

_WINDOWS: list[tuple[str, int]] = [
    ("30s", 30),
    ("2m", 120),
    ("5m", 300),
    ("10m", 600),
]


# ── Overlay ──────────────────────────────────────────────────────

_LEFT_W = 240           # resource list panel width
_ROW_H = 22             # resource list row height
_TOP_STRIP_H = 44       # time-window selector strip
_GRAPH_PAD = 12
_CLOSE_SZ = 32


def _draw_close_button(
    surface: pygame.Surface, rect: pygame.Rect, *, hover: bool,
) -> None:
    """Red-X close button — shared between overlay popups."""
    from compprog_pygame.games.hex_colony.ui_bottom_bar import get_red_x_icon
    bg_col = (60, 20, 20, 220) if hover else (34, 34, 40, 200)
    bg = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    bg.fill(bg_col)
    surface.blit(bg, rect.topleft)
    pygame.draw.rect(surface, (200, 80, 80), rect, width=2, border_radius=4)
    icon = get_red_x_icon(rect.w - 8)
    surface.blit(icon, (rect.x + 4, rect.y + 4))


class AdvancedStatsOverlay(Panel):
    """Full-screen popup with selectable resource graphs and stats."""

    def __init__(self) -> None:
        super().__init__()
        self.visible: bool = False
        self.history: StatsHistory | None = None
        self.tech_tree: "TechTree | None" = None
        self.tier_tracker: "TierTracker | None" = None
        self.god_mode_getter: "callable | None" = None

        self._screen_w = 0
        self._screen_h = 0
        self._close_rect = pygame.Rect(0, 0, 0, 0)
        self._row_rects: list[tuple[pygame.Rect, Resource]] = []
        self._window_rects: list[tuple[pygame.Rect, int]] = []

        # Default: track a handful of common resources.
        self._selected: set[Resource] = {
            Resource.WOOD, Resource.STONE, Resource.FOOD, Resource.IRON,
        }
        self._window_idx: int = 1  # 2m
        self.on_close: "callable | None" = None

    def layout(self, screen_w: int, screen_h: int) -> None:
        self._screen_w = screen_w
        self._screen_h = screen_h
        self.rect = pygame.Rect(0, 0, screen_w, screen_h)

    # ── Helpers ──────────────────────────────────────────────────

    def _god(self) -> bool:
        return bool(self.god_mode_getter and self.god_mode_getter())

    def _visible_resources(self) -> list[Resource]:
        """Resources to show in the picker list, respecting tier/tech gates."""
        god = self._god()
        out: list[Resource] = []
        for res in list(RAW_RESOURCES) + [
            r for r in Resource if r in PROCESSED_RESOURCES
        ]:
            if god or is_resource_available(
                res, self.tech_tree, self.tier_tracker,
            ):
                out.append(res)
        return out

    # ── Drawing ──────────────────────────────────────────────────

    def draw(self, surface: pygame.Surface, world: "World") -> None:
        if not self.visible:
            return

        sw, sh = self._screen_w, self._screen_h
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill(UI_OVERLAY)
        surface.blit(overlay, (0, 0))

        margin = 40
        panel = pygame.Rect(margin, margin, sw - margin * 2, sh - margin * 2)
        content_y = draw_titled_panel(surface, panel, "Advanced Statistics")

        # Close button
        self._close_rect = pygame.Rect(
            panel.right - _CLOSE_SZ - 12, panel.top + 12,
            _CLOSE_SZ, _CLOSE_SZ,
        )
        _draw_close_button(
            surface, self._close_rect,
            hover=self._close_rect.collidepoint(pygame.mouse.get_pos()),
        )

        # Time-window strip
        strip = pygame.Rect(
            panel.x + 12, content_y + 4,
            panel.w - 24, _TOP_STRIP_H,
        )
        self._draw_window_strip(surface, strip)

        # Left resource picker panel
        left = pygame.Rect(
            panel.x + 12, strip.bottom + 6,
            _LEFT_W, panel.bottom - strip.bottom - 18,
        )
        self._draw_resource_list(surface, left)

        # Right graph + stats panel
        right = pygame.Rect(
            left.right + 12, strip.bottom + 6,
            panel.right - (left.right + 12) - 12,
            left.h,
        )
        self._draw_graphs(surface, right, world)

    def _draw_window_strip(
        self, surface: pygame.Surface, rect: pygame.Rect,
    ) -> None:
        label = Fonts.body().render("Time window:", True, UI_TEXT)
        surface.blit(label, (rect.x + 4, rect.centery - label.get_height() // 2))
        x = rect.x + label.get_width() + 14
        y = rect.y + (rect.h - 28) // 2
        self._window_rects = []
        for idx, (text, _seconds) in enumerate(_WINDOWS):
            tw = 52
            r = pygame.Rect(x, y, tw, 28)
            is_sel = idx == self._window_idx
            bg = UI_ACCENT if is_sel else UI_BG
            pygame.draw.rect(surface, bg, r, border_radius=4)
            pygame.draw.rect(surface, UI_BORDER, r, width=1, border_radius=4)
            surf = Fonts.small().render(text, True, UI_TEXT)
            surface.blit(surf, (
                r.centerx - surf.get_width() // 2,
                r.centery - surf.get_height() // 2,
            ))
            self._window_rects.append((r, idx))
            x += tw + 6

    def _draw_resource_list(
        self, surface: pygame.Surface, rect: pygame.Rect,
    ) -> None:
        pygame.draw.rect(surface, UI_BG, rect, border_radius=6)
        pygame.draw.rect(surface, UI_BORDER, rect, width=1, border_radius=6)
        header = Fonts.body().render("Resources", True, UI_ACCENT)
        surface.blit(header, (rect.x + 10, rect.y + 6))

        prev_clip = surface.get_clip()
        surface.set_clip(rect)

        cy = rect.y + 30
        self._row_rects = []
        for res in self._visible_resources():
            row = pygame.Rect(rect.x + 6, cy, rect.w - 12, _ROW_H)
            is_sel = res in self._selected
            if is_sel:
                pygame.draw.rect(surface, (50, 70, 100), row, border_radius=3)
            # Checkbox
            cb = pygame.Rect(row.x + 2, row.y + 2, 16, 16)
            pygame.draw.rect(surface, UI_BG, cb, border_radius=2)
            pygame.draw.rect(surface, UI_BORDER, cb, width=1, border_radius=2)
            if is_sel:
                pygame.draw.line(
                    surface, UI_OK,
                    (cb.x + 3, cb.centery), (cb.centerx, cb.bottom - 3), 2,
                )
                pygame.draw.line(
                    surface, UI_OK,
                    (cb.centerx, cb.bottom - 3), (cb.right - 2, cb.y + 3), 2,
                )
            # Icon
            icon_surf = get_resource_icon(res, 14)
            surface.blit(icon_surf, (cb.right + 6, row.y + 3))
            # Name
            name_x = cb.right + 6 + icon_surf.get_width() + 4
            name_surf = render_text_clipped(
                Fonts.small(),
                res.name.replace("_", " ").title(),
                RESOURCE_COLORS.get(res, UI_TEXT),
                row.right - name_x - 2,
            )
            surface.blit(name_surf, (name_x, row.y + 4))
            self._row_rects.append((row, res))
            cy += _ROW_H
            if cy > rect.bottom - _ROW_H:
                break

        surface.set_clip(prev_clip)

    def _draw_graphs(
        self, surface: pygame.Surface, rect: pygame.Rect, world: "World",
    ) -> None:
        pygame.draw.rect(surface, UI_BG, rect, border_radius=6)
        pygame.draw.rect(surface, UI_BORDER, rect, width=1, border_radius=6)

        if self.history is None:
            return

        window_s = _WINDOWS[self._window_idx][1]

        # Top summary row: population growth + totals
        summary_h = 68
        summary = pygame.Rect(
            rect.x + 8, rect.y + 8, rect.w - 16, summary_h,
        )
        self._draw_summary(surface, summary, world, window_s)

        # Graph area (selected resources)
        graph_rect = pygame.Rect(
            rect.x + 8, summary.bottom + 8,
            rect.w - 16, rect.bottom - summary.bottom - 16,
        )
        pygame.draw.rect(
            surface, (30, 35, 45), graph_rect, border_radius=4,
        )
        pygame.draw.rect(
            surface, UI_BORDER, graph_rect, width=1, border_radius=4,
        )

        selected = [r for r in self._selected]
        if not selected:
            msg = Fonts.body().render(
                "Select one or more resources on the left",
                True, UI_MUTED,
            )
            surface.blit(msg, (
                graph_rect.centerx - msg.get_width() // 2,
                graph_rect.centery - msg.get_height() // 2,
            ))
            return

        # Determine max across selected, over window
        max_val = 1.0
        for res in selected:
            data = self.history.resource(res)
            if not data:
                continue
            n = min(len(data), window_s)
            recent = list(data)[-n:]
            if recent:
                max_val = max(max_val, max(recent))
        # Round the y-axis upward to a nice round number so labels are
        # readable across all scales.
        max_val = _nice_ceiling(max_val)

        # Grid lines (4 horizontal) with value labels.
        plot_x = graph_rect.x + 44
        plot_w = graph_rect.right - plot_x - 4
        plot_h = graph_rect.h - 8
        for i in range(0, 5):
            frac = i / 4.0
            gy = graph_rect.bottom - 4 - int(plot_h * frac)
            if 0 < i < 4:
                pygame.draw.line(
                    surface, (55, 60, 72),
                    (plot_x, gy), (graph_rect.right - 2, gy), 1,
                )
            lbl = Fonts.tiny().render(
                _fmt_axis(max_val * frac), True, UI_MUTED,
            )
            surface.blit(lbl, (
                plot_x - lbl.get_width() - 4,
                gy - lbl.get_height() // 2,
            ))

        # X-axis time labels (window start → "now")
        x_lbl_now = Fonts.tiny().render("now", True, UI_MUTED)
        x_lbl_start = Fonts.tiny().render(
            f"-{_fmt_window_secs(window_s)}", True, UI_MUTED,
        )
        surface.blit(x_lbl_start, (plot_x, graph_rect.bottom - 14))
        surface.blit(x_lbl_now, (
            graph_rect.right - x_lbl_now.get_width() - 4,
            graph_rect.bottom - 14,
        ))

        # Plot each selected resource
        legend_y = graph_rect.y + 4
        legend_x = graph_rect.right - 170
        for res in selected:
            data = self.history.resource(res)
            if len(data) < 2:
                continue
            n = min(len(data), window_s)
            recent = list(data)[-n:]
            color = RESOURCE_COLORS.get(res, (200, 200, 200))
            points: list[tuple[int, int]] = []
            for i, v in enumerate(recent):
                px = plot_x + int(i * plot_w / max(1, n - 1))
                py = (
                    graph_rect.bottom - 4
                    - int((v / max_val) * plot_h)
                )
                points.append((px, py))
            if len(points) >= 2:
                pygame.draw.lines(surface, color, False, points, 2)

            # Legend entry: icon + name + live production rate.
            prod = self.history.production_rate(world, res)
            cons = self.history.consumption_rate(world, res)
            net = prod - cons
            icon_surf = get_resource_icon(res, 12)
            surface.blit(icon_surf, (legend_x, legend_y))
            name_surf = Fonts.tiny().render(
                f"{res.name.replace('_', ' ').title()}  "
                f"{net:+.2f}/s",
                True, color,
            )
            surface.blit(name_surf, (legend_x + 16, legend_y + 1))
            legend_y += 16

    def _draw_summary(
        self, surface: pygame.Surface, rect: pygame.Rect,
        world: "World", window_s: int,
    ) -> None:
        """Row of key aggregate numbers above the graph."""
        if self.history is None:
            return
        # Population growth rate (pop/min)
        pop = list(self.history.population())
        pop_rate = 0.0
        if len(pop) >= 2:
            n = min(len(pop), window_s)
            recent = pop[-n:]
            dt = (len(recent) - 1) * SAMPLE_INTERVAL
            if dt > 0:
                pop_rate = (recent[-1] - recent[0]) / dt * 60.0
        # Live total production rate across selected resources.
        live_prod = sum(
            self.history.production_rate(world, r) for r in self._selected
        )
        stats: list[tuple[str, str, tuple[int, int, int]]] = [
            ("Population", f"{world.population.count}", UI_ACCENT),
            ("Pop/min", f"{pop_rate:+.1f}",
             UI_OK if pop_rate >= 0 else (220, 90, 90)),
            ("Prod/s", f"{live_prod:.2f}",
             UI_OK if live_prod > 0 else UI_MUTED),
            ("Time", _fmt_time(int(world.time_elapsed)), UI_TEXT),
            ("Window", _WINDOWS[self._window_idx][0], UI_MUTED),
        ]
        col_w = rect.w // max(1, len(stats))
        for i, (label, value, col) in enumerate(stats):
            cx = rect.x + col_w * i + col_w // 2
            lbl = Fonts.tiny().render(label, True, UI_MUTED)
            val = Fonts.title().render(value, True, col)
            surface.blit(lbl, (cx - lbl.get_width() // 2, rect.y + 4))
            surface.blit(val, (cx - val.get_width() // 2, rect.y + 20))

    # ── Events ───────────────────────────────────────────────────

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.visible:
            return False

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._close()
            return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._close_rect.collidepoint(event.pos):
                self._close()
                return True
            for r, idx in self._window_rects:
                if r.collidepoint(event.pos):
                    self._window_idx = idx
                    return True
            for r, res in self._row_rects:
                if r.collidepoint(event.pos):
                    if res in self._selected:
                        self._selected.discard(res)
                    else:
                        self._selected.add(res)
                    return True

        # Consume all events while modal is up.
        if hasattr(event, "pos"):
            return True
        return False

    def _close(self) -> None:
        self.visible = False
        if self.on_close is not None:
            self.on_close()


def _fmt_time(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    if m >= 60:
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _fmt_window_secs(s: int) -> str:
    if s < 60:
        return f"{s}s"
    m = s // 60
    return f"{m}m"


def _fmt_axis(v: float) -> str:
    """Compact label for graph axis ticks."""
    if v >= 10000:
        return f"{v / 1000:.0f}k"
    if v >= 1000:
        return f"{v / 1000:.1f}k"
    if v >= 10:
        return f"{int(v)}"
    if v >= 1:
        return f"{v:.1f}"
    return f"{v:.2f}"


def _nice_ceiling(v: float) -> float:
    """Round *v* up to a "nice" power-of-ten multiple (1, 2, 5 × 10^k)
    so the graph axis labels are readable."""
    import math
    if v <= 0:
        return 1.0
    exp = math.floor(math.log10(v))
    base = 10 ** exp
    frac = v / base
    if frac <= 1:
        nice = 1
    elif frac <= 2:
        nice = 2
    elif frac <= 5:
        nice = 5
    else:
        nice = 10
    return float(nice * base)
