import { Tooltip } from "antd";
import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";

import type { Referral } from "../../api/types";
import { REFERRAL_TONE } from "../../design/status";
import {
  buildTimelineLayout,
  durationDays,
  periodLabel,
  type DependencyLink,
  type TimelineBar,
} from "./timelineLayout";

/**
 * The referral stack as a timeline — spec §6.4.
 *
 * Three fixed tracks (Slot 1, Slot 2, Exempt) drawn against a real time axis:
 * every bar is positioned and sized by its own dates, so a referral that ran
 * for a day and one that has been open three weeks cannot look alike. Colour
 * encodes status and nothing else — concurrency is structural, shown by the
 * slot a referral occupies, which is why the Concept Note's legend needed
 * correcting in the first place.
 *
 * Rules that are easy to lose in a refactor:
 *
 *  - **Never colour alone.** Every state is a colour, a word and a mark, so the
 *    picture survives monochrome and colour-blind readers.
 *  - **A short bar still has to be visible and clickable.** Bars have a pixel
 *    floor, and the label moves outside the bar when it will not fit inside.
 *  - **An open referral has no right edge.** It fades into an arrow rather than
 *    being closed off at today, which would read as an outcome.
 *
 * Read-only: clicking a bar reports the id and nothing else, so the §6.2
 * actions stay in ReferralActions where the state machine rules live.
 */

interface Props {
  referrals: Referral[];
  onReferralClick?: (referralId: string) => void;
  selectedReferralId?: string | null;
  /** Injectable for tests; production reads the clock. */
  today?: Date;
  /** Injectable for tests, where there is no layout to measure. */
  width?: number;
}

const GUTTER = 74; // track-label column
const RIGHT_PAD = 16;
const AXIS_HEIGHT = 30;
const ROW_HEIGHT = 30;
const BAR_HEIGHT = 20;
const TRACK_GAP = 10;
const MIN_BAR_PX = 10;
const MIN_CHART_PX = 560;
/** Rough advance width of the 11px label face; good enough to decide fit. */
const CHAR_PX = 5.9;
/** Below this a truncated label is all ellipsis and no information. */
const MIN_LABEL_CHARS = 6;
/** Room a tick label needs before the next one may also be drawn. */
const MIN_TICK_LABEL_PX = 46;

export default function ReferralStackTimeline({
  referrals,
  onReferralClick,
  selectedReferralId = null,
  today,
  width: widthProp,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [measured, setMeasured] = useState(widthProp ?? 900);
  const markerId = useId();

  // Measured rather than assumed: the case screen puts this in a responsive
  // card, so the available width is not known until it is laid out.
  useLayoutEffect(() => {
    if (widthProp !== undefined) return;
    const node = containerRef.current;
    if (!node || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => setMeasured(entry.contentRect.width));
    observer.observe(node);
    return () => observer.disconnect();
  }, [widthProp]);

  useEffect(() => {
    if (widthProp !== undefined) setMeasured(widthProp);
  }, [widthProp]);

  const layout = useMemo(() => buildTimelineLayout(referrals, { today }), [referrals, today]);

  const chartWidth = Math.max(measured - GUTTER - RIGHT_PAD, MIN_CHART_PX);
  const svgWidth = GUTTER + chartWidth + RIGHT_PAD;

  const geometry = useMemo(() => {
    // Each track starts below the last, tall enough for however many rows its
    // bars needed.
    let y = AXIS_HEIGHT;
    const trackTop = new Map<string, number>();
    layout.tracks.forEach((track) => {
      trackTop.set(track.id, y);
      y += track.rowCount * ROW_HEIGHT + TRACK_GAP;
    });
    return { trackTop, height: y };
  }, [layout]);

  if (layout.isEmpty) return null;

  const x = (offset: number) => GUTTER + offset * chartWidth;
  const barY = (bar: TimelineBar) =>
    (geometry.trackTop.get(bar.track) ?? AXIS_HEIGHT) + bar.row * ROW_HEIGHT + (ROW_HEIGHT - BAR_HEIGHT) / 2;

  const bars = layout.tracks.flatMap((track) => track.bars);
  const barById = new Map(bars.map((bar) => [bar.referral.id, bar]));

  // How far a label may run before it hits the next bar sharing its row.
  // Without this a wide bar's overflowing label draws straight across the bar
  // beside it and over that bar's own label.
  // Gridlines stay on every interval, but labels are thinned to whatever the
  // width can hold: twenty-one day labels on a narrow chart would overprint each
  // other, which is the same collision the bar labels had.
  const tickSpacing = chartWidth / Math.max(layout.ticks.length, 1);
  const labelEvery = Math.max(1, Math.ceil(MIN_TICK_LABEL_PX / tickSpacing));

  const rightEdge = GUTTER + chartWidth;
  const roomAfter = new Map<string, number>();
  layout.tracks.forEach((track) => {
    const rows = new Map<number, TimelineBar[]>();
    track.bars.forEach((bar) => rows.set(bar.row, [...(rows.get(bar.row) ?? []), bar]));
    rows.forEach((rowBars) => {
      const sorted = [...rowBars].sort((a, b) => a.offset - b.offset);
      sorted.forEach((bar, index) => {
        const next = sorted[index + 1];
        const barRight = x(bar.offset) + Math.max(bar.width * chartWidth, MIN_BAR_PX);
        const limit = next ? x(next.offset) : rightEdge;
        roomAfter.set(bar.referral.id, limit - barRight);
      });
    });
  });

  return (
    <div ref={containerRef} style={{ width: "100%" }}>
      <div className="t-caps" style={{ marginBottom: 8 }}>
        Referral timeline {layout.yearLabel}
      </div>

      {/* Sideways scroll rather than compression: below ~560px the axis would
          be unreadable squeezed to fit, and scrolling is expected here. */}
      <div style={{ overflowX: "auto" }}>
        <svg
          width={svgWidth}
          height={geometry.height}
          role="img"
          aria-label={`Referral timeline, ${bars.length} referrals`}
        >
          <defs>
            <marker id={markerId} viewBox="0 0 8 8" refX={7} refY={4} markerWidth={6} markerHeight={6} orient="auto">
              <path d="M 0 0 L 8 4 L 0 8 z" fill="var(--ink-400)" />
            </marker>
          </defs>

          {/* Axis: a gridline per interval, a label per interval the width allows. */}
          {layout.ticks.map((tick, index) => (
            <g key={tick.date.toISOString()}>
              <line
                x1={x(tick.offset)}
                y1={AXIS_HEIGHT - 8}
                x2={x(tick.offset)}
                y2={geometry.height}
                stroke="var(--line-soft)"
              />
              {index % labelEvery === 0 && (
                <text
                  x={x(tick.offset)}
                  y={AXIS_HEIGHT - 14}
                  fontSize={10}
                  fill="var(--ink-400)"
                  textAnchor="middle"
                  fontWeight={600}
                >
                  {tick.label}
                </text>
              )}
            </g>
          ))}
          <line
            x1={GUTTER}
            y1={AXIS_HEIGHT - 8}
            x2={GUTTER + chartWidth}
            y2={AXIS_HEIGHT - 8}
            stroke="var(--line)"
          />

          {/* Track labels and their baselines. */}
          {layout.tracks.map((track) => {
            const top = geometry.trackTop.get(track.id) ?? 0;
            return (
              <g key={track.id}>
                <text x={0} y={top + ROW_HEIGHT / 2 + 3} className="t-caps" fontSize={10} fill="var(--ink-400)">
                  {track.label.toUpperCase()}
                </text>
                {track.bars.length === 0 && (
                  <text x={GUTTER + 4} y={top + ROW_HEIGHT / 2 + 4} fontSize={11} fill="var(--ink-400)">
                    Never used
                  </text>
                )}
              </g>
            );
          })}

          {/* Dependency arrows sit under the bars so a connector never covers one. */}
          {layout.links.map((link) => (
            <Connector
              key={`${link.fromId}-${link.toId}`}
              link={link}
              from={barById.get(link.fromId)}
              to={barById.get(link.toId)}
              x={x}
              barY={barY}
              chartWidth={chartWidth}
              markerId={markerId}
            />
          ))}

          {bars.map((bar) => (
            <Bar
              key={bar.referral.id}
              bar={bar}
              x={x}
              y={barY(bar)}
              chartWidth={chartWidth}
              roomAfter={roomAfter.get(bar.referral.id) ?? 0}
              selected={selectedReferralId === bar.referral.id}
              onClick={onReferralClick}
            />
          ))}
        </svg>
      </div>

      <Legend />
    </div>
  );
}

function Bar({
  bar,
  x,
  y,
  chartWidth,
  roomAfter,
  selected,
  onClick,
}: {
  bar: TimelineBar;
  x: (offset: number) => number;
  y: number;
  chartWidth: number;
  /** Pixels before the next bar on this row — the label may not cross it. */
  roomAfter: number;
  selected: boolean;
  onClick?: (id: string) => void;
}) {
  const r = bar.referral;
  const tone = REFERRAL_TONE[r.status];

  const left = x(bar.offset);
  // The pixel floor lives here rather than in the layout: a same-day referral is
  // a real zero-width interval, and only the renderer knows how wide a pixel is.
  const width = Math.max(bar.width * chartWidth, MIN_BAR_PX);

  const label = `${tone.mark} ${r.referral_category_label} · ${r.receiving_partner_detail.partner_name}`;

  // Where the label goes, in order of preference:
  //  1. inside the bar, truncated to fit — the label then moves with the bar
  //     and can never run over its neighbour;
  //  2. beside it, but only as far as the next bar on this row allows;
  //  3. nowhere, leaving the tooltip to carry it. A label that overlaps the bar
  //     next to it is worse than no label at all.
  const insideChars = Math.floor((width - 14) / CHAR_PX);
  const outsideChars = Math.floor((roomAfter - (bar.isOpenEnded ? 16 : 9)) / CHAR_PX);
  const placeInside = insideChars >= MIN_LABEL_CHARS;
  const shownLabel = placeInside
    ? truncate(label, insideChars)
    : outsideChars >= MIN_LABEL_CHARS
      ? truncate(label, outsideChars)
      : "";

  const tooltip = (
    <div>
      <div style={{ fontWeight: 600 }}>
        {tone.mark} {r.status_display}
      </div>
      <div style={{ fontSize: 12 }}>{label}</div>
      <div style={{ fontSize: 12 }}>{periodLabel(bar)}</div>
      <div style={{ fontSize: 12 }}>
        {durationDays(bar)} day{durationDays(bar) === 1 ? "" : "s"}
        {bar.isOpenEnded ? " so far" : ""}
      </div>
    </div>
  );

  return (
    <Tooltip title={tooltip} mouseEnterDelay={0.1}>
      <g
        role="button"
        tabIndex={0}
        aria-label={`${label}, ${r.status_display}, ${periodLabel(bar)}`}
        data-testid={`bar-${r.id}`}
        style={{ cursor: onClick ? "pointer" : "default" }}
        onClick={() => onClick?.(r.id)}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onClick?.(r.id);
          }
        }}
      >
        <rect
          x={left}
          y={y}
          width={width}
          height={BAR_HEIGHT}
          rx={4}
          fill={tone.bar}
          stroke={selected ? "var(--ink-900)" : "transparent"}
          strokeWidth={selected ? 2 : 0}
        />

        {/* An open referral has no closing edge: it runs into an arrow rather
            than being squared off at today, which would read as an outcome. */}
        {bar.isOpenEnded && (
          <path
            d={`M ${left + width} ${y} l 7 ${BAR_HEIGHT / 2} l -7 ${BAR_HEIGHT / 2} z`}
            fill={tone.bar}
            opacity={0.7}
          />
        )}

        {shownLabel && (
          <text
            x={placeInside ? left + 7 : left + width + (bar.isOpenEnded ? 14 : 7)}
            y={y + BAR_HEIGHT / 2 + 4}
            fontSize={11}
            fontWeight={600}
            fill={placeInside ? onDark(r.status) : tone.ink}
          >
            {shownLabel}
          </text>
        )}
      </g>
    </Tooltip>
  );
}

/**
 * The connector from a referral to the one it produced.
 *
 * Drawn as an elbow — out of the parent's right edge, down (or up) to the
 * child's row, then into the child's left edge — so a link spanning tracks does
 * not cut across the bars between them.
 */
function Connector({
  link,
  from,
  to,
  x,
  barY,
  chartWidth,
  markerId,
}: {
  link: DependencyLink;
  from?: TimelineBar;
  to?: TimelineBar;
  x: (offset: number) => number;
  barY: (bar: TimelineBar) => number;
  chartWidth: number;
  markerId: string;
}) {
  if (!from || !to) return null;

  const fromX = x(from.offset) + Math.max(from.width * chartWidth, MIN_BAR_PX);
  const toX = x(to.offset);
  const fromY = barY(from) + BAR_HEIGHT / 2;
  const toY = barY(to) + BAR_HEIGHT / 2;

  // Step out past the parent's close but never past the child's start, so the
  // path stays inside the gap it describes even when the two nearly touch.
  const elbow = Math.max(fromX + 6, Math.min(fromX + 16, toX - 6));

  return (
    <g aria-hidden>
      <path
        d={`M ${fromX} ${fromY} H ${elbow} V ${toY} H ${toX}`}
        fill="none"
        stroke="var(--ink-400)"
        strokeWidth={1.25}
        markerEnd={`url(#${markerId})`}
      />
      <text
        x={elbow + 3}
        y={(fromY + toY) / 2 - 2}
        fontSize={9}
        fill="var(--ink-600)"
        // Halo, so the label stays readable where it crosses a gridline.
        stroke="var(--surface)"
        strokeWidth={3}
        paintOrder="stroke"
      >
        {link.kind}
      </text>
    </g>
  );
}

/** Text colour for a label sitting on a filled bar. */
function onDark(status: Referral["status"]): string {
  // Pending Confirmation is the one pale fill; everything else takes white.
  return status === "PENDING_CONFIRMATION" ? "var(--gold-700)" : "#ffffff";
}

function truncate(value: string, max: number): string {
  if (max <= 0) return "";
  return value.length <= max ? value : `${value.slice(0, Math.max(1, max - 1))}…`;
}

const LEGEND_ORDER = ["PENDING_CONFIRMATION", "ACTIVE", "COMPLETED", "FAILED", "REPLACED", "CANCELLED"] as const;

const LEGEND_LABEL: Record<(typeof LEGEND_ORDER)[number], string> = {
  PENDING_CONFIRMATION: "Pending confirmation",
  ACTIVE: "Active",
  COMPLETED: "Completed",
  FAILED: "Failed",
  REPLACED: "Replaced",
  CANCELLED: "Cancelled",
};

function Legend() {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 16px", marginTop: 10 }}>
      {LEGEND_ORDER.map((status) => {
        const tone = REFERRAL_TONE[status];
        return (
          <span key={status} style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12 }}>
            <span
              aria-hidden
              style={{ width: 14, height: 10, borderRadius: 3, background: tone.bar, display: "inline-block" }}
            />
            <span style={{ color: tone.ink, fontWeight: 600 }}>
              {tone.mark} {LEGEND_LABEL[status]}
            </span>
          </span>
        );
      })}
    </div>
  );
}
