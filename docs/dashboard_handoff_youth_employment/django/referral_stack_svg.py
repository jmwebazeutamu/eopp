"""
Server-rendered referral stack timeline.

Reference implementation for CASE_MANAGER_DASHBOARD.md §6. Copy into
``apps/referrals/rendering.py`` and wire into the case detail template.

Design notes, all of which are requirements rather than preferences:

* No charting library. This is a rectangle-and-line layout problem. The output
  is a few KB of inline SVG, renders identically on any Android browser, prints,
  and costs one HTTP request. A chart library would cost hundreds of KB on a 3G
  connection to draw the same rectangles.

* State is encoded redundantly: colour AND shape AND a text label. WCAG 1.4.1.
  A hollow dashed bar with a diamond end-cap reads as "failed" in greyscale, in
  bright sunlight, and to a colour-blind reader.

* Dead time is drawn explicitly. The valuable insight in a referral stack is the
  gap between a failure and its replacement, and bars alone hide it.

* The caller MUST render the chronological event table beneath this SVG. That
  table is the WCAG 1.1.1 text alternative and the low-end-browser fallback.

Colours here are the design-system STATUS tokens from
``../../design_handoff_youth_employment/README.md``: green/gold/terra/red, each
reserved for one state and always paired with a shape and a word. They are a
different palette from the four-slot validated CATEGORICAL series palette in
``../README.md`` §8.4, which is for charts where colour carries identity rather
than state. Do not mix the two: a status colour used as "series 4" is a defect,
and so is a series colour used to mean "failed".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from html import escape
from typing import Iterable, Sequence

# --- design tokens ----------------------------------------------------------
INK_900 = "#1A1915"
INK_400 = "#7A7568"
LINE_SOFT = "#F4F1EA"
LINE = "#E3DED2"
GREEN_700 = "#0F4F3C"
GREEN_500 = "#12836B"
GOLD_500 = "#D08A0A"    # below 3:1 vs surface: MUST carry a visible label, never fill alone
TERRA_500 = "#A84B2A"   # design-system STATUS token (replaced), not a series colour
TERRA_700 = "#8A3A1E"
RED_500 = "#B3261E"     # design-system STATUS token (failed), not a series colour
RED_700 = "#8C1D18"
INK_MUTED = "#4E4A42"
GOLD_INK = "#7A5308"    # accessible text colour for gold; the fill itself is not

# --- layout constants -------------------------------------------------------
LANE_HEIGHT = 46
BAR_HEIGHT = 20
LABEL_WIDTH = 150
RIGHT_GUTTER = 120       # room for the terminal-state text label
TOP_AXIS = 26
BOTTOM_PAD = 32
MIN_BAR_WIDTH = 8        # a one-day interval must still be visible
PX_PER_DAY_MIN = 1.6     # below this, switch the axis to months


@dataclass(frozen=True)
class ReferralLane:
    """One referral, flattened for rendering.

    Mirrors the ``ReferralTimelineItem`` contract in
    ../../REFERRAL_STACK_TIMELINE_COMPONENT_PROMPT.md so the React component and
    this renderer never diverge. If one changes, change both.
    """
    referral_id: str
    referral_category: str
    receiving_partner_name: str
    status: str                    # pending_confirmation|active|completed|failed|replaced|cancelled
    referral_trigger: str          # manual|onward|replacement
    initiated_date: date
    confirmed_date: date | None = None
    outcome_date: date | None = None
    failure_reason_code: str | None = None
    parent_referral_id: str | None = None
    parallel_group_id: str | None = None

    @property
    def end_date(self) -> date | None:
        return self.outcome_date

    @property
    def is_terminal(self) -> bool:
        return self.status in ("completed", "failed", "replaced", "cancelled")


def render_referral_stack(
    lanes: Sequence[ReferralLane],
    *,
    as_of: date | None = None,
    width: int = 900,
    youth_label: str = "",
) -> str:
    """Return a complete inline ``<svg>`` element as a string.

    Returns an empty-state ``<p>`` when there are no referrals, rather than an
    empty chart frame: an empty chart reads as a rendering failure.
    """
    if not lanes:
        return '<p class="empty">No referrals recorded for this case yet.</p>'

    as_of = as_of or date.today()
    lanes = sorted(lanes, key=lambda r: (r.initiated_date, r.referral_id))

    start = min(r.initiated_date for r in lanes)
    end = max([r.end_date or as_of for r in lanes] + [as_of])
    span_days = max((end - start).days, 1)

    plot_left = LABEL_WIDTH
    plot_width = width - LABEL_WIDTH - RIGHT_GUTTER
    px_per_day = plot_width / span_days

    # Long histories scroll horizontally rather than compressing. Do not squeeze
    # 18 months into 320px; the caller wraps this in an overflow-x container.
    if px_per_day < PX_PER_DAY_MIN:
        plot_width = int(span_days * PX_PER_DAY_MIN)
        width = plot_width + LABEL_WIDTH + RIGHT_GUTTER
        px_per_day = PX_PER_DAY_MIN

    height = TOP_AXIS + len(lanes) * LANE_HEIGHT + BOTTOM_PAD

    def x(d: date) -> float:
        return plot_left + (d - start).days * px_per_day

    parts: list[str] = []
    aria = escape(
        f"Referral stack timeline for {youth_label or 'this case'}: "
        f"{len(lanes)} referrals between {start:%d %b %Y} and {end:%d %b %Y}. "
        f"Full detail in the event table below."
    )
    parts.append(
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
        f'role="img" aria-label="{aria}" '
        f'font-family="Archivo, sans-serif">'
    )

    parts.extend(_month_grid(start, end, x, TOP_AXIS, height - BOTTOM_PAD))

    lane_y: dict[str, float] = {}
    for i, r in enumerate(lanes):
        y = TOP_AXIS + i * LANE_HEIGHT
        lane_y[r.referral_id] = y
        parts.extend(_render_lane(r, y, x, as_of))

    parts.extend(_render_dead_time(lanes, lane_y, x))

    # "today" rule
    tx = x(as_of)
    parts.append(
        f'<line x1="{tx:.1f}" y1="{TOP_AXIS}" x2="{tx:.1f}" y2="{height - BOTTOM_PAD}" '
        f'stroke="{INK_900}" stroke-width="1.5"/>'
        f'<text x="{tx + 4:.1f}" y="{height - BOTTOM_PAD - 4}" font-size="10.5" '
        f'font-weight="700" fill="{INK_900}">Today</text>'
    )
    parts.append(
        f'<line x1="{plot_left - 10}" y1="{height - BOTTOM_PAD}" x2="{width}" '
        f'y2="{height - BOTTOM_PAD}" stroke="{LINE}" stroke-width="1"/>'
    )
    parts.append("</svg>")
    return "".join(parts)


def _month_grid(start: date, end: date, x, y_top: int, y_bottom: int) -> Iterable[str]:
    """Solid hairline gridlines, one per month. Never dashed: dashing reads as
    a threshold or a projection when it is only a grid."""
    cur = date(start.year, start.month, 1)
    while cur <= end:
        if cur >= start:
            gx = x(cur)
            yield (
                f'<line x1="{gx:.1f}" y1="{y_top}" x2="{gx:.1f}" y2="{y_bottom}" '
                f'stroke="{LINE_SOFT}" stroke-width="1"/>'
                f'<text x="{gx:.1f}" y="{y_top - 8}" font-size="11" fill="{INK_400}">'
                f'{cur:%b}</text>'
            )
        cur = date(cur.year + (cur.month // 12), (cur.month % 12) + 1, 1)


def _render_lane(r: ReferralLane, y: float, x, as_of: date) -> Iterable[str]:
    label_y = y + 14
    yield (
        f'<text x="0" y="{label_y}" font-size="12" font-weight="600" fill="{INK_900}">'
        f'{escape(_lane_title(r))}</text>'
        f'<text x="0" y="{label_y + 13}" font-size="10.5" fill="{INK_400}">'
        f'{escape(r.receiving_partner_name)}</text>'
    )

    pending_end = r.confirmed_date or r.outcome_date or as_of
    x0, x1 = x(r.initiated_date), x(pending_end)
    pending_w = max(x1 - x0, MIN_BAR_WIDTH)

    # Pending interval: always gold, always drawn, even when it is one day.
    #
    # GOLD_500 sits below 3:1 against the page, so it may never carry meaning by
    # fill alone (README §8.4). The wait in days is rendered as visible text, not
    # only in the <title> tooltip: hover is the interaction least available to
    # these users, and a tooltip-only value fails WCAG 1.1.1.
    wait_days = (r.confirmed_date - r.initiated_date).days if r.confirmed_date else (as_of - r.initiated_date).days
    yield (
        f'<rect x="{x0:.1f}" y="{y}" width="{pending_w:.1f}" height="{BAR_HEIGHT}" '
        f'rx="3" fill="{GOLD_500}">'
        f'<title>Pending confirmation · {r.initiated_date:%d %b}'
        f'{f" → {r.confirmed_date:%d %b} ({wait_days} days)" if r.confirmed_date else f" · not yet confirmed, {wait_days} days"}'
        f'</title></rect>'
    )
    if pending_w >= 26:
        # label inside the bar only when it fits with padding
        yield (
            f'<text x="{x0 + pending_w / 2:.1f}" y="{y + 14}" font-size="10.5" '
            f'font-weight="700" fill="#231A04" text-anchor="middle">{wait_days}d</text>'
        )
    else:
        yield (
            f'<text x="{x0 + pending_w + 4:.1f}" y="{y - 2}" font-size="10" '
            f'font-weight="700" fill="{GOLD_INK}">{wait_days}d wait</text>'
        )

    if r.confirmed_date:
        active_end = r.outcome_date or as_of
        ax0 = x(r.confirmed_date) + 2          # 2px surface gap between fills
        ax1 = x(active_end)
        active_w = max(ax1 - ax0, MIN_BAR_WIDTH)

        if r.status == "failed":
            # hollow + dashed: reads as "failed" in greyscale and in sunlight
            yield (
                f'<rect x="{ax0:.1f}" y="{y}" width="{active_w:.1f}" height="{BAR_HEIGHT}" '
                f'rx="3" fill="none" stroke="{RED_500}" stroke-width="2" stroke-dasharray="4 3">'
                f'<title>Active, then failed'
                f'{f" · {escape(r.failure_reason_code)}" if r.failure_reason_code else ""}</title></rect>'
            )
        else:
            yield (
                f'<rect x="{ax0:.1f}" y="{y}" width="{active_w:.1f}" height="{BAR_HEIGHT}" '
                f'rx="3" fill="{GREEN_500}">'
                f'<title>Active · {r.confirmed_date:%d %b} → '
                f'{r.outcome_date:%d %b}</title></rect>'
                if r.outcome_date else
                f'<rect x="{ax0:.1f}" y="{y}" width="{active_w:.1f}" height="{BAR_HEIGHT}" '
                f'rx="3" fill="{GREEN_500}"><title>Active since '
                f'{r.confirmed_date:%d %b}</title></rect>'
            )

    yield from _end_cap(r, y, x)


def _end_cap(r: ReferralLane, y: float, x) -> Iterable[str]:
    """Shape carries the terminal state; the text label repeats it in words."""
    if not r.is_terminal or not r.outcome_date:
        if r.status == "active":
            yield (
                f'<text x="{x(date.today()) + 10:.1f}" y="{y + 15}" font-size="11" '
                f'font-weight="700" fill="{GREEN_700}">Active</text>'
            )
        return

    cx = x(r.outcome_date)
    cy = y + BAR_HEIGHT / 2

    if r.status == "completed":
        yield (
            f'<polygon points="{cx:.1f},{cy - 8:.1f} {cx + 7:.1f},{cy + 6:.1f} '
            f'{cx - 7:.1f},{cy + 6:.1f}" fill="{GREEN_700}"/>'
            f'<text x="{cx + 14:.1f}" y="{y + 15}" font-size="11" font-weight="700" '
            f'fill="{GREEN_700}">Completed</text>'
        )
    elif r.status == "failed":
        yield (
            f'<polygon points="{cx:.1f},{cy - 8:.1f} {cx + 8:.1f},{cy:.1f} '
            f'{cx:.1f},{cy + 8:.1f} {cx - 8:.1f},{cy:.1f}" fill="{RED_500}"/>'
            f'<text x="{cx + 15:.1f}" y="{y + 15}" font-size="11" font-weight="700" '
            f'fill="{RED_700}">Failed'
            f'{": " + escape(_humanise(r.failure_reason_code)) if r.failure_reason_code else ""}'
            f'</text>'
        )
    elif r.status == "replaced":
        yield (
            f'<rect x="{cx - 6:.1f}" y="{cy - 6:.1f}" width="12" height="12" '
            f'fill="{TERRA_500}" transform="rotate(45 {cx:.1f} {cy:.1f})"/>'
            f'<text x="{cx + 14:.1f}" y="{y + 15}" font-size="11" font-weight="700" '
            f'fill="{TERRA_700}">Replaced</text>'
        )
    else:  # cancelled
        yield (
            f'<line x1="{cx - 7:.1f}" y1="{cy:.1f}" x2="{cx + 7:.1f}" y2="{cy:.1f}" '
            f'stroke="{INK_400}" stroke-width="3"/>'
            f'<text x="{cx + 14:.1f}" y="{y + 15}" font-size="11" font-weight="600" '
            f'fill="{INK_MUTED}">Cancelled</text>'
        )


def _render_dead_time(lanes, lane_y, x) -> Iterable[str]:
    """Dotted connector from a failed referral to its replacement, labelled with
    the gap in days.

    This is the whole point of the component. "Failed 18 Jun, replacement raised
    3 Jul" is a supervision finding; two bars on separate rows are not.
    """
    by_id = {r.referral_id: r for r in lanes}
    for child in lanes:
        parent = by_id.get(child.parent_referral_id or "")
        if parent is None or parent.outcome_date is None:
            continue
        gap = (child.initiated_date - parent.outcome_date).days
        if gap <= 0:
            continue

        py = lane_y[parent.referral_id] + BAR_HEIGHT / 2
        cy = lane_y[child.referral_id] + BAR_HEIGHT / 2
        px_, cx_ = x(parent.outcome_date), x(child.initiated_date)
        mid = (py + cy) / 2

        # Route DOWN out of the parent lane, across in the gutter between lanes,
        # then down into the child. Never straight across at bar height: that
        # path runs through the parent's terminal-state text label.
        yield (
            f'<path d="M {px_:.1f} {py + BAR_HEIGHT / 2:.1f} V {mid:.1f} '
            f'H {cx_:.1f} V {cy - BAR_HEIGHT / 2:.1f}" fill="none" '
            f'stroke="{TERRA_500}" stroke-width="1.5" stroke-dasharray="3 3"/>'
            f'<text x="{px_ + 6:.1f}" y="{mid - 5:.1f}" font-size="10.5" '
            f'font-weight="700" fill="{TERRA_700}">{gap} days dead time</text>'
        )


def _lane_title(r: ReferralLane) -> str:
    trigger = {"onward": " (onward)", "replacement": " (replacement)"}.get(r.referral_trigger, "")
    return f"{_humanise(r.referral_category)}{trigger}"


def _humanise(code: str | None) -> str:
    return (code or "").replace("_", " ").capitalize()


# -----------------------------------------------------------------------------
# Tests to write alongside this module (see CASE_MANAGER_DASHBOARD.md §8)
# -----------------------------------------------------------------------------
# 1. A single-day referral still renders a visible bar (MIN_BAR_WIDTH).
# 2. A failed referral renders a dashed stroke and no solid fill.
# 3. A replacement with a 15-day gap renders a connector labelled "15 days dead time".
# 4. An 18-month history widens the SVG rather than compressing px_per_day.
# 5. Two referrals sharing a parallel_group_id render on separate lanes that
#    overlap in x: never merged into one lane.
# 6. Output contains no <script> and no external references (CSP-safe, printable).
# 7. Partner names and failure codes are HTML-escaped.
# 8. An empty lane list returns the empty-state paragraph, not an empty <svg>.
# 9. Every gold pending bar has a visible day-count label, inside the bar when it
#    fits and outside it when it does not: never a tooltip alone.
# 10. Only colours from the validated palette in README §8.4 appear in the output.
