import { Tooltip } from "antd";
import { useId, useMemo } from "react";

import type { LinkageStatus, ServiceLinkage } from "../../api/types";
import { LINKAGE_TONE } from "../../design/wltStatus";
import {
  buildTimelineScale,
  parseTimelineDate,
  TimelineAxis,
  TimelineBarGlyph,
  TimelineLaneLabel,
  TimelineLegend,
  TIMELINE_AXIS_HEIGHT,
  TIMELINE_BAR_HEIGHT,
  TIMELINE_ROW_HEIGHT,
  timelineX,
  type TimelineLegendItem,
  type TimelineTone,
} from "../../components/timeline/TimelinePrimitives";

const WIDTH = 900;
const GUTTER = 82;
const RIGHT_PAD = 16;
const LABEL_RESERVE = 300;
const TRACK_GAP = 10;
const MARKER_WIDTH = 18;
const MIN_LANES = 3;
const UNKNOWN_TONE: TimelineTone = {
  fill: "var(--fill-muted-2)",
  ink: "var(--ink-600)",
  border: "var(--closed-border)",
  mark: "?",
};

type DatedLinkage = { linkage: ServiceLinkage; date: Date; lane: number };

function toneFor(status: string): TimelineTone {
  const tone = LINKAGE_TONE[status as LinkageStatus];
  return tone
    ? { fill: tone.bg, ink: tone.fg, border: tone.bd, mark: tone.mark }
    : UNKNOWN_TONE;
}

function labelFor(linkage: ServiceLinkage) {
  return `${linkage.type_label} · ${linkage.provider_name ?? "No provider"}`;
}

export default function LinkageTimeline({
  linkages,
  onLinkageClick,
  today,
}: {
  linkages: ServiceLinkage[];
  onLinkageClick?: (linkage: ServiceLinkage) => void;
  today?: Date;
}) {
  const markerId = `linkage-arrow-${useId().replace(/:/g, "")}`;
  const layout = useMemo(() => {
    const undated: ServiceLinkage[] = [];
    const dated = linkages
      .map((linkage) => {
        const date = parseTimelineDate(linkage.opened_on);
        if (!date) undated.push(linkage);
        return date ? { linkage, date } : null;
      })
      .filter((item): item is Omit<DatedLinkage, "lane"> => item !== null)
      .sort(
        (a, b) =>
          a.date.getTime() - b.date.getTime() ||
          a.linkage.id.localeCompare(b.linkage.id),
      );

    // A linkage gets a stable visual lane. Unlike a duration bar, its marker's
    // readable label extends to the right; immediately reusing a lane would
    // make labels collide even when the recorded periods do not overlap.
    const placed: DatedLinkage[] = dated.map((item, lane) => ({
      ...item,
      lane,
    }));
    const scale = buildTimelineScale(
      placed.map((item) => item.date),
      today,
    );
    return {
      placed,
      undated,
      scale,
      lanes: Math.max(MIN_LANES, placed.length + 1),
    };
  }, [linkages, today]);

  if (!linkages.length) return null;

  const chartWidth = WIDTH - GUTTER - RIGHT_PAD;
  const datedWidth = chartWidth - LABEL_RESERVE;
  const x = (offset: number) => timelineX(GUTTER, datedWidth, offset);
  const laneTop = (lane: number) =>
    TIMELINE_AXIS_HEIGHT + lane * (TIMELINE_ROW_HEIGHT + TRACK_GAP);
  const markerY = (lane: number) =>
    laneTop(lane) + (TIMELINE_ROW_HEIGHT - TIMELINE_BAR_HEIGHT) / 2;
  const height =
    TIMELINE_AXIS_HEIGHT + layout.lanes * (TIMELINE_ROW_HEIGHT + TRACK_GAP);
  const placedById = new Map(
    layout.placed.map((item) => [item.linkage.id, item]),
  );
  const usedStatuses = new Set(
    layout.placed.map((item) => item.linkage.status),
  );
  const legend: TimelineLegendItem[] = [...usedStatuses].map((status) => ({
    key: status,
    label:
      layout.placed.find((item) => item.linkage.status === status)?.linkage
        .status_display ?? status,
    tone: toneFor(status),
  }));

  return (
    <div style={{ width: "100%" }}>
      <div className="t-caps" style={{ marginBottom: 8 }}>
        Linkage timeline {layout.scale.yearLabel}
      </div>
      <div style={{ overflowX: "auto" }}>
        <svg
          width={WIDTH}
          height={height}
          role="img"
          aria-label={`Linkage timeline, ${layout.placed.length} dated linkages`}
          style={{ display: "block" }}
        >
          <defs>
            <marker
              id={markerId}
              viewBox="0 0 8 8"
              refX="7"
              refY="4"
              markerWidth="6"
              markerHeight="6"
              orient="auto"
            >
              <path d="M 0 0 L 8 4 L 0 8 z" fill="var(--ink-400)" />
            </marker>
          </defs>
          <TimelineAxis
            ticks={layout.scale.ticks}
            x={x}
            chartStart={GUTTER}
            chartEnd={GUTTER + datedWidth}
            height={height}
          />
          {Array.from({ length: layout.lanes }, (_, lane) => (
            <TimelineLaneLabel
              key={lane}
              label={`Lane ${lane + 1}`}
              top={laneTop(lane)}
              gutter={GUTTER}
              empty={!layout.placed.some((item) => item.lane === lane)}
            />
          ))}
          {layout.placed.map((item) => {
            const parent = item.linkage.predecessor
              ? placedById.get(item.linkage.predecessor)
              : undefined;
            if (!parent) return null;
            const fromX = x(layout.scale.position(parent.date)) + MARKER_WIDTH;
            const toX = x(layout.scale.position(item.date));
            const fromY = markerY(parent.lane) + TIMELINE_BAR_HEIGHT / 2;
            const toY = markerY(item.lane) + TIMELINE_BAR_HEIGHT / 2;
            const elbow = Math.max(fromX + 6, Math.min(fromX + 18, toX - 6));
            return (
              <path
                key={`onward-${item.linkage.id}`}
                data-testid={`onward-${item.linkage.id}`}
                d={`M ${fromX} ${fromY} H ${elbow} V ${toY} H ${toX}`}
                fill="none"
                stroke="var(--ink-400)"
                strokeWidth={1.25}
                markerEnd={`url(#${markerId})`}
              />
            );
          })}
          {layout.placed.map((item) => {
            const tone = toneFor(item.linkage.status);
            const left = x(layout.scale.position(item.date));
            const label = `${tone.mark} ${labelFor(item.linkage)}`;
            return (
              <Tooltip
                key={item.linkage.id}
                title={`${label} · ${item.linkage.status_display} · ${item.linkage.opened_on}`}
              >
                <g
                  role={onLinkageClick ? "button" : undefined}
                  tabIndex={onLinkageClick ? 0 : undefined}
                  aria-label={`${label}, ${item.linkage.status_display}, ${item.linkage.opened_on}`}
                  data-testid={`linkage-marker-${item.linkage.id}`}
                  style={{ cursor: onLinkageClick ? "pointer" : "default" }}
                  onClick={() => onLinkageClick?.(item.linkage)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onLinkageClick?.(item.linkage);
                    }
                  }}
                >
                  <TimelineBarGlyph
                    left={left}
                    y={markerY(item.lane)}
                    width={MARKER_WIDTH}
                    tone={tone}
                    label={label}
                    labelX={left + MARKER_WIDTH + 7}
                    labelFill={tone.ink}
                  />
                </g>
              </Tooltip>
            );
          })}
        </svg>
      </div>
      <TimelineLegend items={legend} />
      {layout.undated.length > 0 && (
        <div
          className="t-meta"
          data-testid="undated-linkages"
          style={{ marginTop: 8 }}
        >
          {layout.undated.length} linkage
          {layout.undated.length === 1 ? "" : "s"} not shown because no opening
          date was recorded.
        </div>
      )}
    </div>
  );
}
