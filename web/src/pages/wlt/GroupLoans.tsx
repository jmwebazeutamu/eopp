import { App } from "antd";
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, errorMessage } from "../../api/client";
import type { Paginated, WltGroup, WltLoan, WltMeeting } from "../../api/types";
import { Button, CapsLabel, Card } from "../../components/ui";
import { useLang } from "../../i18n/LanguageContext";

/**
 * The group's loans, on the group screen.
 *
 * Lending itself happens at a meeting — the cash leaves the box in the room and
 * the till has to balance around it — so the *writes* stay there. But nothing
 * on the group screen showed a loan or pointed at lending, so anyone looking
 * for "the loan screen" looked here and found a readiness column reading
 * "Outstanding principal 0 ETB" with no way in. This is the way in.
 *
 * Outstanding loans lead; settled ones follow as history. A group that has
 * repaid four loans is a different group from one that has never lent, and
 * completed cycles is a phase-gate condition — so the settled rows are the
 * evidence for it rather than clutter.
 */
export default function GroupLoans({ group }: { group: WltGroup }) {
  const { message } = App.useApp();
  const { t } = useLang();
  const navigate = useNavigate();

  const [loans, setLoans] = useState<WltLoan[]>([]);
  const [openMeeting, setOpenMeeting] = useState<WltMeeting | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // The open meeting too, so the panel can offer the way in rather than
      // only naming it. One call each; neither depends on the other.
      const [rows, meetings] = await Promise.all([
        api.get<WltLoan[]>(`/wlt/groups/${group.id}/loans/`),
        api.get<Paginated<WltMeeting> | WltMeeting[]>("/wlt/meetings/", {
          params: { group: group.id, status: "OPEN", page_size: 1 },
        }),
      ]);
      setLoans(rows.data);
      const open = Array.isArray(meetings.data) ? meetings.data : meetings.data.results;
      setOpenMeeting(open[0] ?? null);
    } catch (error) {
      message.error(errorMessage(error, t("wlt.loansLoadFailed")));
    } finally {
      setLoading(false);
    }
  }, [group.id, message, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const outstanding = loans.filter((loan) => loan.status === "DISBURSED");
  const settled = loans.filter((loan) => loan.status !== "DISBURSED");

  return (
    <Card className="card--tight">
      <div style={{ display: "flex", gap: 12, alignItems: "baseline", justifyContent: "space-between" }}>
        <span style={{ display: "flex", gap: 10, alignItems: "baseline" }}>
          <CapsLabel>{t("wlt.loans")}</CapsLabel>
          <span className="t-meta">{t("wlt.loansCount", { count: outstanding.length })}</span>
        </span>
        {openMeeting && (
          <Button size="sm" onClick={() => navigate(`/wlt/groups/${group.id}/meetings/${openMeeting.id}`)}>
            {t("wlt.lendAtMeeting")}
          </Button>
        )}
      </div>

      {loading && loans.length === 0 && <p className="t-meta">{t("common.loading")}</p>}

      {!loading && loans.length === 0 && (
        <>
          <p style={{ marginTop: 8 }}>{t("wlt.noLoans")}</p>
          <p className="t-meta">{t("wlt.noLoansBody")}</p>
        </>
      )}

      {/* Named rather than assumed. Lending is recorded at a meeting, and
          without one open there is nothing to press — so the panel says where
          the action lives instead of showing a button that goes nowhere. */}
      {!openMeeting && loans.length === 0 && !loading && (
        <p className="t-meta">{t("wlt.lendNeedsMeeting")}</p>
      )}

      {outstanding.length > 0 && (
        <table className="roster-table">
          <tbody>
            {outstanding.map((loan) => (
              <tr key={loan.id}>
                <td style={{ fontWeight: 600 }}>{loan.borrower_name}</td>
                <td className="t-meta">
                  {t(`wlt.purpose${loan.purpose}`)} · {t("wlt.loanDue", { date: loan.due_on })}
                </td>
                <td className="tabular">
                  {t("wlt.outstanding")} {loan.outstanding_principal_etb} ETB
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {settled.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <CapsLabel>{t("wlt.settledLoans")}</CapsLabel>
          <p className="t-meta">{t("wlt.settledLoansBody")}</p>
          <table className="roster-table">
            <tbody>
              {settled.map((loan) => (
                <tr key={loan.id}>
                  <td className="t-meta" colSpan={3}>
                    {loan.borrower_name} · {loan.principal_etb} ETB · {t(`wlt.loanStatus${loan.status}`)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
