import type { Finance } from "./types";
import { formatMoney } from "./format";

/**
 * Money card. Total savings is the headline; principal outstanding is the
 * number that needs action, so it carries the terracotta token and sits on
 * its own rule at the foot of the card.
 */
export function SavingsSummaryCard({ finance }: { finance: Finance }) {
  const outstanding = Number(finance.principal_outstanding);
  const borrowed = Number(finance.loans_received_total);
  const outstandingPct = borrowed > 0 ? Math.round((outstanding / borrowed) * 100) : 0;

  return (
    <section className="card" aria-labelledby="finance-heading">
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "var(--s3)", marginBottom: "var(--s4)" }}>
        <div className="t-caps" id="finance-heading">Savings and loans</div>
        <span className="t-meta">All groups</span>
      </div>

      <div className="money-well" style={{ marginBottom: "var(--s4)" }}>
        <div className="money-well__label">Total savings</div>
        <div className="money-well__value">
          {formatMoney(finance.savings_total)}{" "}
          <span className="money-well__unit">{finance.currency}</span>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "var(--s4)" }}>
        <div>
          <div className="t-meta">Loans received</div>
          <div className="t-metric-sm" style={{ fontSize: 20 }}>{formatMoney(finance.loans_received_total)}</div>
          <div className="t-meta">{finance.loan_count} loan{finance.loan_count === 1 ? "" : "s"}</div>
        </div>
        <div>
          <div className="t-meta">Repaid</div>
          <div className="t-metric-sm" style={{ fontSize: 20 }}>{formatMoney(finance.repayments_total)}</div>
          <div className="t-meta">
            {formatMoney(finance.repayments_principal)} principal ·{" "}
            {formatMoney(finance.repayments_service_charge)} charges
          </div>
        </div>
      </div>

      {outstanding > 0 && (
        <div className="money-outstanding">
          <div>
            <div style={{ fontSize: 13, fontWeight: 600 }}>Principal outstanding</div>
            <div className="t-meta">{outstandingPct}% of the loan still to repay</div>
          </div>
          <div className="money-outstanding__value">{formatMoney(finance.principal_outstanding)}</div>
        </div>
      )}
    </section>
  );
}
