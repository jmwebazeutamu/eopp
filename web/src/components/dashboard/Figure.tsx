import type { MeanDays, Rate } from "../../api/types";
import { useLang } from "../../i18n/LanguageContext";

/**
 * How a banded figure renders.
 *
 * One component, because the rule it enforces is one rule: a percentage never
 * appears without the counts it came from, and a percentage the denominator
 * cannot support does not appear at all. Written once so it cannot be forgotten
 * on the disaggregated cell nobody looked at — which is where denominators
 * collapse.
 *
 * The provisional marker is an asterisk *and* a tooltip *and* a muted denominator
 * line, not a colour: this has to survive a monochrome screen like every other
 * status in the system.
 */

export function RateValue({ rate, bold = true }: { rate: Rate; bold?: boolean }) {
  const { t } = useLang();

  if (rate.percent === null) {
    return (
      <span className="tabular" style={{ color: "var(--ink-400)" }} title={rate.note}>
        — <span style={{ fontSize: 12 }}>{t("dash.tooFew")}</span>
      </span>
    );
  }

  return (
    <span className="tabular" style={{ fontWeight: bold ? 600 : 400 }} title={rate.note || undefined}>
      {rate.percent}%{rate.band === "provisional" && <sup title={rate.note}>*</sup>}
    </span>
  );
}

export function MeanValue({ mean }: { mean: MeanDays }) {
  const { t } = useLang();

  if (mean.days === null) {
    return (
      <span className="tabular" style={{ color: "var(--ink-400)" }} title={mean.note}>
        — <span style={{ fontSize: 12 }}>{t("dash.tooFew")}</span>
      </span>
    );
  }

  return (
    <span className="tabular" style={{ fontWeight: 600 }} title={mean.note || undefined}>
      {mean.days === 1 ? t("dash.day") : t("dash.days", { days: mean.days })}
      {mean.band === "provisional" && <sup title={mean.note}>*</sup>}
    </span>
  );
}

/**
 * The footnote a screen carrying provisional figures owes its reader.
 *
 * Rendered once per panel rather than per row, and only when something on that
 * panel is actually marked.
 */
export function ProvisionalNote({ shown }: { shown: boolean }) {
  const { t } = useLang();
  if (!shown) return null;
  return (
    <div className="t-meta" style={{ marginTop: 8 }}>
      {t("dash.provisionalNote")}
    </div>
  );
}
