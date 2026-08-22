import type { WltMeeting } from "../../api/types";
import { useLang } from "../../i18n/LanguageContext";
import { buildFundSeries, polylinePoints } from "./fundSeries";

/**
 * The group fund over its last twelve closed meetings.
 *
 * A polyline and two rules — no chart library, per the brief's 3G constraint.
 * The arithmetic is in `fundSeries.ts` and tested there; this draws it.
 *
 * The y-axis is anchored at zero. A self-scaling axis turns a 0.5% wobble into
 * a cliff, which on a savings ledger is the difference between "steady" and
 * "something happened".
 *
 * A point is marked only on a **fall** of more than half. A fund that doubles
 * week to week is an ordinary early group, and marking growth teaches the
 * reader to ignore the mark. A fall is money leaving the box — a loan or a
 * problem, and from this list the two cannot be told apart, so the caption
 * says "check", not "wrong".
 */
export default function FundTrend({ meetings }: { meetings: WltMeeting[] }) {
  const { t } = useLang();
  const series = buildFundSeries(meetings);

  if (series.points.length === 0) {
    return <p className="t-meta">{t("wlt.fundTrendEmpty")}</p>;
  }

  const dropped = series.points.filter((point) => point.notable);
  const last = series.points[series.points.length - 1];

  return (
    <figure style={{ margin: "12px 0 0" }}>
      <figcaption className="t-meta" style={{ marginBottom: 6 }}>
        {t("wlt.fundTrend", { count: series.points.length })}
      </figcaption>

      <svg
        viewBox={`0 0 ${series.width} ${series.height}`}
        width="100%"
        height={series.height}
        role="img"
        /* The figures are in the table below; the shape is the only thing the
           picture adds, so that is what the label describes. */
        aria-label={t("wlt.fundTrend", { count: series.points.length })}
        preserveAspectRatio="none"
        style={{ display: "block", overflow: "visible" }}
      >
        <line
          x1={0}
          x2={series.width}
          y1={series.midY}
          y2={series.midY}
          stroke="var(--line-soft)"
          strokeWidth={1}
        />
        {series.baselineY !== null && (
          <line
            x1={0}
            x2={series.width}
            y1={series.baselineY}
            y2={series.baselineY}
            stroke="var(--line)"
            strokeWidth={1}
          />
        )}
        <polyline
          points={polylinePoints(series)}
          fill="none"
          stroke="var(--green-700)"
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
        {series.points.map((point) => (
          <circle
            key={point.meetingNo}
            cx={point.x}
            cy={point.y}
            r={point.notable ? 4 : point === last ? 3 : 0}
            fill={point.notable ? "var(--terra-500)" : "var(--green-700)"}
          />
        ))}
      </svg>

      <div
        className="t-meta"
        style={{ display: "flex", justifyContent: "space-between", marginTop: 4 }}
      >
        <span className="tabular">{series.points[0].heldOn}</span>
        <span className="tabular">{last.heldOn}</span>
      </div>

      {/* Named in words as well as marked on the line, so the finding survives
          a monochrome screen and a reader who does not study the dots. */}
      {dropped.map((point) => (
        <p key={point.meetingNo} className="t-meta" style={{ color: "var(--terra-700)", marginTop: 4 }}>
          {t("wlt.fundTrendDrop", { no: point.meetingNo })}
        </p>
      ))}
    </figure>
  );
}
