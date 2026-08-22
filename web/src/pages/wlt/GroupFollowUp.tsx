import { useNavigate } from "react-router-dom";

import type { GateCondition, WltMemberSavingsCompliance } from "../../api/types";
import { Button, CapsLabel, Card } from "../../components/ui";
import { useLang } from "../../i18n/LanguageContext";
import { BAND_STYLE, summarise, thresholdFrom } from "./compliance";

/**
 * What needs chasing this week.
 *
 * The signal this card exists for was previously a single cell in row 14 of a
 * twenty-row table and was never stated in words. A group at 20% savings
 * compliance was as easy to miss as one at 95%.
 *
 * Three wells, then the members furthest below the bar, worst first — the
 * roster sorted by name buries exactly the people the card is for.
 *
 * The bar is the group's **own** gate threshold, read off its readiness
 * conditions rather than hard-coded, so this card and the readiness tile can
 * never disagree about who is compliant. It is configuration: effective-dated
 * and geography-scoped, and it currently reads 80 rather than the 90 that
 * appears in some copy.
 */
export default function GroupFollowUp({
  groupId,
  members,
  conditions,
}: {
  groupId: string;
  members: WltMemberSavingsCompliance[];
  conditions: GateCondition[] | undefined;
}) {
  const { t } = useLang();
  const navigate = useNavigate();

  const threshold = thresholdFrom(conditions);
  const summary = summarise(members, threshold);

  // Nothing recorded at all is not "everybody compliant". A group with no
  // meetings behind it would otherwise read as a clean bill of health.
  if (summary.counted === 0) {
    return (
      <Card className="card--tight">
        <CapsLabel>{t("wlt.followUp")}</CapsLabel>
        <p className="t-meta" style={{ marginTop: 8 }}>
          {t("wlt.followUpNothingMeasured")}
        </p>
      </Card>
    );
  }

  const clean = summary.belowThreshold === 0;

  return (
    <Card className="card--tight">
      <div style={{ display: "flex", gap: 12, alignItems: "baseline", justifyContent: "space-between" }}>
        <CapsLabel>{t("wlt.followUp")}</CapsLabel>
        <Button size="sm" onClick={() => navigate(`/wlt/groups/${groupId}/members`)}>
          {t("wlt.followUpAllMembers")}
        </Button>
      </div>

      {/* Stated in words, which is the whole point. A number in a table cell is
          not a finding until somebody reads the table. */}
      <p style={{ margin: "10px 0 0", fontWeight: 600 }}>
        {clean
          ? t("wlt.followUpClean", { threshold })
          : t("wlt.followUpSummary", { count: summary.belowThreshold, threshold })}
      </p>

      <div className="stat-wells">
        <Well label={t("wlt.followUpCompliant")} value={summary.compliant} tone="compliant" />
        <Well
          label={t("wlt.followUpBelow", { threshold })}
          value={summary.belowThreshold}
          tone={summary.belowThreshold > 0 ? "at-risk" : "compliant"}
        />
        {/* Shown only when there are any: a permanent "0 not yet recorded"
            well is a row of furniture on a group that is up to date. */}
        {summary.unmeasured > 0 && (
          <Well label={t("wlt.followUpUnmeasured")} value={summary.unmeasured} tone="watch" />
        )}
      </div>

      {summary.lowest.length > 0 && (
        <table className="roster-table" style={{ marginTop: 12 }}>
          <tbody>
            {summary.lowest.map((row) => {
              const style = BAND_STYLE[row.band];
              return (
                <tr key={row.person_id}>
                  <td style={{ fontWeight: 600 }}>{row.full_name}</td>
                  <td className="t-meta">
                    {t("wlt.followUpMet", { met: row.meetings_met, expected: row.meetings_expected })}
                  </td>
                  <td>
                    {/* Length encodes the value as well as colour, so the bands
                        still read in greyscale. */}
                    <span className="meter" aria-hidden>
                      <span
                        className="meter__fill"
                        style={{ width: `${Math.min(100, row.pct)}%`, background: style.fill }}
                      />
                    </span>
                  </td>
                  <td className="tabular" style={{ textAlign: "right", fontWeight: 700, color: style.fg }}>
                    {row.pct}% <span className="t-meta">{style.label}</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </Card>
  );
}

function Well({ label, value, tone }: { label: string; value: number; tone: keyof typeof BAND_STYLE }) {
  return (
    <div className="stat-well">
      <span className="t-meta">{label}</span>
      <strong className="tabular" style={{ color: BAND_STYLE[tone].fg }}>
        {value}
      </strong>
    </div>
  );
}
