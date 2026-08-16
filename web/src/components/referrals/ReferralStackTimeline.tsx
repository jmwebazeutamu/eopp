import { Empty, Tooltip, Typography } from "antd";
import { scaleTime } from "d3-scale";
import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";

import type { Referral, ReferralStatusCode } from "../../api/types";
import { buildTimelineLayout, type DependencyArrow, type TimelineBar } from "./timelineLayout";

/**
 * The referral stack as a timeline — spec §6.4, and the live version of the
 * Concept Note's Figure 4.
 *
 * One lane per referral on a real time axis. Two deliberate departures from that
 * mockup, both from `docs/REFERRAL_STACK_TIMELINE_COMPONENT_PROMPT.md`:
 *
 * 1. Colour encodes `status` and nothing else. The mockup's legend spent two of
 *    its five colours on "parallel", which is not a status but a structural fact
 *    (`parallel_group_id`) that is independent of it — a Complementary Service
 *    referral can be parallel *and* failed, which that scheme cannot draw.
 *    Concurrency is shown here as a bracket down the left edge instead.
 * 2. The x-axis is real time scaled to the case, not "Month 1..6" bands.
 *
 * Read-only by design: clicking a bar reports the id and nothing else, so the
 * §6.2 actions stay in ReferralActions where the state machine rules live.
 */

interface Props {
  referrals: Referral[];
  onReferralClick?: (referralId: string) => void;
  /** Drawn with a focus ring, so a selection made elsewhere is findable here. */
  selectedReferralId?: string | null;
  /** Injectable for tests; production reads the clock. */
  today?: Date;
  /** Injectable for tests, where there is no layout to measure. */
  width?: number;
}

/**
 * Status colours for the timeline.
 *
 * Deliberately not `REFERRAL_STATUS_COLOURS`: those are Ant Design tag palette
 * names for the list and detail views, and SVG needs real values. The mapping
 * also differs on purpose — the prompt's table reads the bars as a lifecycle
 * (amber in flight, green ended well, red ended badly) rather than as six
 * unrelated categories.
 */
const STATUS_FILL: Record<ReferralStatusCode, string> = {
  PENDING_CONFIRMATION: "#e6f0fa",
  ACTIVE: "#fa8c16",
  COMPLETED: "#52c41a",
  FAILED: "#ff4d4f",
  REPLACED: "#ff4d4f",
  CANCELLED: "#bfbfbf",
};

const STATUS_STROKE: Record<ReferralStatusCode, string> = {
  PENDING_CONFIRMATION: "#7ba7d7",
  ACTIVE: "#d46b08",
  COMPLETED: "#389e0d",
  FAILED: "#cf1322",
  REPLACED: "#cf1322",
  CANCELLED: "#8c8c8c",
};

/** Five distinct fills for six statuses: Replaced reuses Failed and adds a mark. */
const LEGEND: { label: string; status: ReferralStatusCode; note?: string }[] = [
  { label: "Completed", status: "COMPLETED" },
  { label: "Active", status: "ACTIVE" },
  { label: "Failed", status: "FAILED" },
  { label: "Pending confirmation", status: "PENDING_CONFIRMATION" },
  { label: "Cancelled", status: "CANCELLED" },
  { label: "Replaced", status: "REPLACED", note: "Failed, with a replacement raised" },
];

const GUTTER = 200;
const RIGHT_PAD = 28;
const AXIS_HEIGHT = 26;
const LANE_HEIGHT = 34;
const BAR_HEIGHT = 18;
const BRACKET_X = GUTTER - 12;
const MIN_CHART_WIDTH = 320;
const MIN_BAR_WIDTH = 3;

function laneY(lane: number): number {
  return AXIS_HEIGHT + lane * LANE_HEIGHT;
}

function barY(lane: number): number {
  return laneY(lane) + (LANE_HEIGHT - BAR_HEIGHT) / 2;
}

function barMidY(lane: number): number {
  return laneY(lane) + LANE_HEIGHT / 2;
}

function truncate(value: string, max: number): string {
  return value.length <= max ? value : `${value.slice(0, max - 1)}…`;
}

/** Full detail on hover, per bar — what the truncated lane label leaves out. */
function tooltipFor(bar: TimelineBar) {
  const r = bar.referral;
  const rows: [string, string][] = [
    ["Category", r.referral_category_label],
    ["Partner", r.receiving_partner_detail.partner_name],
    ["Trigger", r.trigger_display],
    ["Initiated", r.initiated_date],
  ];
  if (r.outcome_date) rows.push(["Outcome recorded", r.outcome_date]);
  if (r.outcome_type_label) rows.push(["Outcome", r.outcome_type_label]);
  if (r.failure_date) rows.push(["Failed", r.failure_date]);
  if (r.failure_reason_label) rows.push(["Reason", r.failure_reason_label]);
  if (bar.isOpenEnded) rows.push(["Still running", "no outcome recorded yet"]);

  return (
    <div>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{r.status_display}</div>
      {rows.map(([label, value]) => (
        <div key={label} style={{ fontSize: 12 }}>
          {label}: {value}
        </div>
      ))}
    </div>
  );
}

/**
 * Elbow path from the parent bar's close to the child bar's start.
 *
 * Drawn as three segments rather than a straight line so an arrow spanning
 * several lanes does not cut across the bars between them.
 */
function arrowPath(fromX: number, fromLane: number, toX: number, toLane: number): string {
  const y1 = barMidY(fromLane);
  const y2 = barMidY(toLane);
  // Step out past the parent's end, but never past the child's start, so the
  // path stays inside the span it describes even when the two nearly touch.
  const elbowX = Math.max(fromX + 8, Math.min(fromX + 18, toX - 8));
  return `M ${fromX} ${y1} H ${elbowX} V ${y2} H ${toX}`;
}

export default function ReferralStackTimeline({
  referrals,
  onReferralClick,
  selectedReferralId = null,
  today,
  width: widthProp,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [measured, setMeasured] = useState(widthProp ?? 960);
  const [hoveredGroup, setHoveredGroup] = useState<string | null>(null);
  const markerId = useId();

  // Measure rather than assume: the case screen puts this in a responsive grid
  // column, so the available width is not known until it is laid out.
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

  const chartWidth = Math.max(measured - GUTTER - RIGHT_PAD, MIN_CHART_WIDTH);
  const scale = useMemo(
    () => scaleTime().domain(layout.domain).range([GUTTER, GUTTER + chartWidth]),
    [layout.domain, chartWidth],
  );

  if (!referrals.length) {
    return <Empty description="No referrals yet" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  const height = AXIS_HEIGHT + layout.laneCount * LANE_HEIGHT + 8;
  const svgWidth = GUTTER + chartWidth + RIGHT_PAD;

  function renderBar(bar: TimelineBar) {
    const r = bar.referral;
    const x = scale(bar.start);
    const width = Math.max(scale(bar.end) - x, MIN_BAR_WIDTH);
    const inHoveredGroup = hoveredGroup !== null && r.parallel_group_id === hoveredGroup;
    const isSelected = selectedReferralId === r.id;

    return (
      <Tooltip key={r.id} title={tooltipFor(bar)} mouseEnterDelay={0.15}>
        <g
          role="button"
          tabIndex={0}
          aria-label={`${r.referral_category_label} referral to ${r.receiving_partner_detail.partner_name}, ${r.status_display}`}
          style={{ cursor: onReferralClick ? "pointer" : "default", outline: "none" }}
          onClick={() => onReferralClick?.(r.id)}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              onReferralClick?.(r.id);
            }
          }}
          onMouseEnter={() => setHoveredGroup(r.parallel_group_id)}
          onMouseLeave={() => setHoveredGroup(null)}
        >
          {/* Full-width hit area: a three-pixel bar is not a clickable target. */}
          <rect x={GUTTER} y={laneY(bar.lane)} width={chartWidth} height={LANE_HEIGHT} fill="transparent" />
          <rect
            data-testid={`bar-${r.id}`}
            x={x}
            y={barY(bar.lane)}
            width={width}
            height={BAR_HEIGHT}
            rx={3}
            fill={STATUS_FILL[r.status]}
            stroke={isSelected || inHoveredGroup ? "#1668dc" : STATUS_STROKE[r.status]}
            strokeWidth={isSelected || inHoveredGroup ? 2 : 1}
            strokeDasharray={r.status === "PENDING_CONFIRMATION" ? "4 3" : undefined}
            opacity={r.status === "CANCELLED" ? 0.55 : 1}
          />
          {/* Replaced shares the Failed colour, so it needs a mark of its own. */}
          {r.status === "REPLACED" && (
            <text
              x={x + width / 2}
              y={barY(bar.lane) + BAR_HEIGHT - 5}
              textAnchor="middle"
              fontSize={11}
              fill="#fff"
              aria-hidden
            >
              ⟳
            </text>
          )}
          {/* An open-ended bar gets no right edge — nothing has closed it yet. */}
          {bar.isOpenEnded && (
            <path
              d={`M ${x + width} ${barY(bar.lane)} l 6 ${BAR_HEIGHT / 2} l -6 ${BAR_HEIGHT / 2} z`}
              fill={STATUS_FILL[r.status]}
              opacity={0.65}
            />
          )}
        </g>
      </Tooltip>
    );
  }

  function renderArrow(arrow: DependencyArrow) {
    const fromX = scale(arrow.fromDate);
    const toX = scale(arrow.toDate);
    const path = arrowPath(fromX, arrow.fromLane, toX, arrow.toLane);
    const labelX = Math.max(fromX + 10, Math.min(fromX + 20, toX - 6));

    return (
      <g key={`${arrow.fromId}-${arrow.toId}`} aria-hidden>
        <path d={path} fill="none" stroke="#8c8c8c" strokeWidth={1.25} markerEnd={`url(#${markerId})`} />
        <text
          x={labelX + 4}
          y={(barMidY(arrow.fromLane) + barMidY(arrow.toLane)) / 2}
          fontSize={10}
          fill="#595959"
          // Halo so the label stays readable where it crosses a bar.
          stroke="#fff"
          strokeWidth={3}
          paintOrder="stroke"
        >
          {arrow.kind}
        </text>
      </g>
    );
  }

  return (
    <div ref={containerRef} style={{ width: "100%" }}>
      <svg
        width={svgWidth}
        height={height}
        role="img"
        aria-label={`Referral timeline, ${layout.laneCount} referrals`}
        style={{ maxWidth: "100%", overflow: "visible" }}
      >
        <defs>
          <marker id={markerId} viewBox="0 0 8 8" refX={7} refY={4} markerWidth={7} markerHeight={7} orient="auto">
            <path d="M 0 0 L 8 4 L 0 8 z" fill="#8c8c8c" />
          </marker>
        </defs>

        {/* Axis */}
        {layout.ticks.map((tick) => {
          const x = scale(tick.date);
          return (
            <g key={tick.date.toISOString()}>
              <line x1={x} y1={AXIS_HEIGHT - 6} x2={x} y2={height} stroke="#f0f0f0" strokeWidth={1} />
              <text x={x} y={AXIS_HEIGHT - 12} fontSize={11} fill="#8c8c8c" textAnchor="middle">
                {tick.label}
              </text>
            </g>
          );
        })}
        <line x1={GUTTER} y1={AXIS_HEIGHT - 6} x2={GUTTER + chartWidth} y2={AXIS_HEIGHT - 6} stroke="#d9d9d9" />

        {/* Lane labels: category and partner, truncated — the bar's tooltip has the rest. */}
        {layout.bars.map((bar) => (
          <text
            key={`label-${bar.referral.id}`}
            x={0}
            y={barMidY(bar.lane) + 4}
            fontSize={12}
            fill={selectedReferralId === bar.referral.id ? "#1668dc" : "#262626"}
            fontWeight={selectedReferralId === bar.referral.id ? 600 : 400}
          >
            {truncate(
              `${bar.referral.referral_category_label} · ${bar.referral.receiving_partner_detail.partner_name}`,
              30,
            )}
          </text>
        ))}

        {/* Parallel groups: a bracket, not a colour. */}
        {layout.brackets.map((bracket) => {
          const top = laneY(bracket.firstLane) + 6;
          const bottom = laneY(bracket.lastLane) + LANE_HEIGHT - 6;
          const active = hoveredGroup === bracket.groupId;
          return (
            <g key={bracket.groupId} data-testid={`bracket-${bracket.groupId}`} aria-hidden>
              <path
                d={`M ${BRACKET_X + 5} ${top} H ${BRACKET_X} V ${bottom} H ${BRACKET_X + 5}`}
                fill="none"
                stroke={active ? "#1668dc" : "#13c2c2"}
                strokeWidth={active ? 2 : 1.5}
              />
              <text
                x={BRACKET_X - 3}
                y={(top + bottom) / 2 + 3}
                fontSize={9}
                fill={active ? "#1668dc" : "#13c2c2"}
                textAnchor="end"
              >
                parallel
              </text>
            </g>
          );
        })}

        {layout.arrows.map(renderArrow)}
        {layout.bars.map(renderBar)}
      </svg>

      <Legend />
    </div>
  );
}

function Legend() {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 16, marginTop: 8, paddingLeft: 4 }}>
      {LEGEND.map((entry) => (
        <Tooltip key={entry.label} title={entry.note}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <svg width={16} height={12} aria-hidden>
              <rect
                x={0}
                y={0}
                width={16}
                height={12}
                rx={2}
                fill={STATUS_FILL[entry.status]}
                stroke={STATUS_STROKE[entry.status]}
                strokeDasharray={entry.status === "PENDING_CONFIRMATION" ? "3 2" : undefined}
                opacity={entry.status === "CANCELLED" ? 0.55 : 1}
              />
              {entry.status === "REPLACED" && (
                <text x={8} y={10} textAnchor="middle" fontSize={9} fill="#fff">
                  ⟳
                </text>
              )}
            </svg>
            <Typography.Text style={{ fontSize: 12 }}>{entry.label}</Typography.Text>
          </span>
        </Tooltip>
      ))}
      <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
        <svg width={16} height={12} aria-hidden>
          <path d="M 6 1 H 1 V 11 H 6" fill="none" stroke="#13c2c2" strokeWidth={1.5} />
        </svg>
        <Typography.Text style={{ fontSize: 12 }}>Parallel (ran concurrently)</Typography.Text>
      </span>
    </div>
  );
}
