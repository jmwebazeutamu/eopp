import { useNavigate } from "react-router-dom";

import type { ServiceLinkage } from "../../api/types";
import { LINKAGE_TONE } from "../../design/wltStatus";
import { useLang } from "../../i18n/LanguageContext";
import { buildLanes } from "./linkageLanes";

/**
 * A group's linkages as labelled lanes.
 *
 * Replaces a timeline with four unlabelled lanes, a three-day axis and labels
 * that ran past the right edge. Each linkage is a row: type and partner in a
 * fixed label column, one status marker on the day something last happened.
 *
 * Built from divs on a CSS grid rather than SVG. The markers are text — a
 * status word has to be readable and translatable, and Amharic runs longer
 * than English — and text in SVG cannot wrap or be selected. The arithmetic
 * lives in `linkageLanes.ts` and is tested there.
 *
 * A marker near either edge anchors to it rather than centring, so nothing
 * escapes the plotting area. That is the fault this replaces, and the same one
 * `timelineLayout.ts` records: a label that does not fit must not escape.
 */
export default function LinkageLanes({ linkages }: { linkages: ServiceLinkage[] }) {
  const { t } = useLang();
  const navigate = useNavigate();
  const { lanes, axis } = buildLanes(linkages);

  if (lanes.length === 0) return null;

  return (
    <div className="lanes">
      <div className="lanes__axis" aria-hidden>
        <div className="lanes__label-col" />
        <div className="lanes__plot">
          {axis.ticks.map((tick) => (
            <span key={tick.date} className="lanes__tick" style={{ left: `${tick.position * 100}%` }}>
              {tick.date.slice(5)}
            </span>
          ))}
        </div>
      </div>

      {/* The axis is nominal when everything happened on one day: three
          linkages opened this morning is ordinary, and an axis implying a
          spread would be inventing one. */}
      {axis.singleDay && <p className="t-meta">{t("wlt.lanesSingleDay", { date: lanes[0].date })}</p>}

      <ul className="lanes__list">
        {lanes.map((lane) => {
          const tone = LINKAGE_TONE[lane.status];
          return (
            <li key={lane.id} className="lanes__row">
              <div className="lanes__label-col">
                <button type="button" className="row-link" onClick={() => navigate(`/wlt/linkages/${lane.id}`)}>
                  {lane.label}
                </button>
                <span className="t-meta lanes__partner">{lane.partner ?? t("wlt.noProvider")}</span>
              </div>

              <div className="lanes__plot">
                <span className="lanes__rule" aria-hidden />
                <span
                  className="lanes__marker"
                  data-anchor={lane.anchor}
                  style={{ left: `${lane.position * 100}%` }}
                >
                  <span
                    className="chip"
                    style={{ color: tone.fg, background: tone.bg, borderColor: tone.bd }}
                    /* The date is on the chip's title rather than beside it:
                       a second text node per lane doubled the row height and
                       is already in the table below. */
                    title={lane.date}
                  >
                    <span className="chip__mark" aria-hidden>
                      {tone.mark}
                    </span>
                    {lane.statusLabel}
                  </span>
                </span>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
