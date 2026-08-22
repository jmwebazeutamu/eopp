export interface TimelineTone {
  fill: string;
  ink: string;
  mark: string;
  border?: string;
}

export interface SharedTimelineTick {
  offset: number;
  label: string;
  date: Date;
}

export interface TimelineLegendItem {
  key: string;
  label: string;
  tone: TimelineTone;
}

export const TIMELINE_AXIS_HEIGHT = 30;
export const TIMELINE_ROW_HEIGHT = 30;
export const TIMELINE_BAR_HEIGHT = 20;
export const TIMELINE_MIN_BAR_PX = 10;
const DAY_MS = 86_400_000;

type TickKind = "day" | "week" | "month" | "quarter";
const INTERVALS: Record<TickKind, TimeInterval> = {
  day: timeDay,
  week: timeMonday,
  month: timeMonth,
  quarter: timeMonth.every(3) as TimeInterval,
};
const DAY_MONTH = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
});
const MONTH = new Intl.DateTimeFormat("en-GB", { month: "short" });
const MONTH_YEAR = new Intl.DateTimeFormat("en-GB", {
  month: "short",
  year: "numeric",
});

export function parseTimelineDate(
  value: string | null | undefined,
): Date | null {
  if (!value) return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (!match) return null;
  const date = new Date(
    Number(match[1]),
    Number(match[2]) - 1,
    Number(match[3]),
  );
  return Number.isNaN(date.getTime()) ? null : date;
}

export function buildTimelineScale(dates: Date[], todayValue = new Date()) {
  const today = new Date(
    todayValue.getFullYear(),
    todayValue.getMonth(),
    todayValue.getDate(),
  );
  if (!dates.length) {
    return {
      domain: [today, today] as [Date, Date],
      ticks: [] as SharedTimelineTick[],
      tickKind: "week" as TickKind,
      position: () => 0,
      yearLabel: String(today.getFullYear()),
    };
  }
  const first = new Date(Math.min(...dates.map((date) => date.getTime())));
  const last = new Date(
    Math.max(today.getTime(), ...dates.map((date) => date.getTime())),
  );
  const rawSpan = Math.max(last.getTime() - first.getTime(), DAY_MS);
  const pad = Math.max(DAY_MS, rawSpan * 0.04);
  const domainStart = new Date(first.getTime() - pad);
  const domainEnd = new Date(last.getTime() + pad);
  const span = domainEnd.getTime() - domainStart.getTime();
  const position = (date: Date) =>
    (date.getTime() - domainStart.getTime()) / span;
  const spanDays = span / DAY_MS;
  const kind: TickKind =
    spanDays <= 21
      ? "day"
      : spanDays <= 120
        ? "week"
        : spanDays <= 730
          ? "month"
          : "quarter";
  const ticks = INTERVALS[kind]
    .range(domainStart, domainEnd)
    .map((date, index) => ({
      date,
      offset: position(date),
      label:
        kind === "day" || kind === "week"
          ? DAY_MONTH.format(date)
          : kind === "month"
            ? date.getMonth() === 0 || index === 0
              ? MONTH_YEAR.format(date)
              : MONTH.format(date)
            : MONTH_YEAR.format(date),
    }));
  const startYear = domainStart.getFullYear();
  const endYear = domainEnd.getFullYear();
  return {
    domain: [domainStart, domainEnd] as [Date, Date],
    ticks,
    tickKind: kind,
    position,
    yearLabel:
      startYear === endYear ? String(startYear) : `${startYear}–${endYear}`,
  };
}

export function timelineX(gutter: number, chartWidth: number, offset: number) {
  return gutter + offset * chartWidth;
}

export function TimelineAxis({
  ticks,
  x,
  chartStart,
  chartEnd,
  height,
  labelEvery = 1,
}: {
  ticks: SharedTimelineTick[];
  x: (offset: number) => number;
  chartStart: number;
  chartEnd: number;
  height: number;
  labelEvery?: number;
}) {
  return (
    <>
      {ticks.map((tick, index) => (
        <g key={tick.date.toISOString()}>
          <line
            x1={x(tick.offset)}
            y1={TIMELINE_AXIS_HEIGHT - 8}
            x2={x(tick.offset)}
            y2={height}
            stroke="var(--line-soft)"
          />
          {index % labelEvery === 0 && (
            <text
              x={x(tick.offset)}
              y={TIMELINE_AXIS_HEIGHT - 14}
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
        x1={chartStart}
        y1={TIMELINE_AXIS_HEIGHT - 8}
        x2={chartEnd}
        y2={TIMELINE_AXIS_HEIGHT - 8}
        stroke="var(--line)"
      />
    </>
  );
}

export function TimelineLaneLabel({
  label,
  top,
  gutter,
  empty,
}: {
  label: string;
  top: number;
  gutter: number;
  empty: boolean;
}) {
  return (
    <g>
      <text
        x={0}
        y={top + TIMELINE_ROW_HEIGHT / 2 + 3}
        className="t-caps"
        fontSize={10}
        fill="var(--ink-400)"
      >
        {label.toUpperCase()}
      </text>
      {empty && (
        <text
          x={gutter + 4}
          y={top + TIMELINE_ROW_HEIGHT / 2 + 4}
          fontSize={11}
          fill="var(--ink-400)"
        >
          Never used
        </text>
      )}
    </g>
  );
}

export function TimelineBarGlyph({
  left,
  y,
  width,
  tone,
  label,
  labelX,
  labelFill,
  openEnded = false,
  selected = false,
}: {
  left: number;
  y: number;
  width: number;
  tone: TimelineTone;
  label?: string;
  labelX?: number;
  labelFill?: string;
  openEnded?: boolean;
  selected?: boolean;
}) {
  return (
    <>
      <rect
        x={left}
        y={y}
        width={width}
        height={TIMELINE_BAR_HEIGHT}
        rx={4}
        fill={tone.fill}
        stroke={selected ? "var(--ink-900)" : (tone.border ?? "transparent")}
        strokeWidth={selected ? 2 : tone.border ? 1 : 0}
      />
      {openEnded && (
        <path
          d={`M ${left + width} ${y} l 7 ${TIMELINE_BAR_HEIGHT / 2} l -7 ${TIMELINE_BAR_HEIGHT / 2} z`}
          fill={tone.fill}
          opacity={0.7}
        />
      )}
      {label && (
        <text
          x={labelX ?? left + 7}
          y={y + TIMELINE_BAR_HEIGHT / 2 + 4}
          fontSize={11}
          fontWeight={600}
          fill={labelFill ?? tone.ink}
        >
          {label}
        </text>
      )}
    </>
  );
}

export function TimelineLegend({ items }: { items: TimelineLegendItem[] }) {
  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: "6px 16px",
        marginTop: 10,
      }}
    >
      {items.map(({ key, label, tone }) => (
        <span
          key={key}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            fontSize: 12,
          }}
        >
          <span
            aria-hidden
            style={{
              width: 14,
              height: 10,
              borderRadius: 3,
              background: tone.fill,
              border: tone.border ? `1px solid ${tone.border}` : undefined,
              display: "inline-block",
            }}
          />
          <span style={{ color: tone.ink, fontWeight: 600 }}>
            {tone.mark} {label}
          </span>
        </span>
      ))}
    </div>
  );
}
import { timeDay, timeMonday, timeMonth, type TimeInterval } from "d3-time";
