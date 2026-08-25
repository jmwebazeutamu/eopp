import type { BeneficiaryDetail } from "./types";
import { BeneficiaryIdentityHeader } from "./BeneficiaryIdentityHeader";
import { PathwayStageList } from "./PathwayStageList";
import { SavingsSummaryCard } from "./SavingsSummaryCard";
import { formatDate, formatDateWithAgo } from "./format";

/**
 * Route: /wlt/beneficiaries/:id
 *
 * Layout contract:
 *   .page > .stack            vertical rhythm, 16px gap, max-width 1180
 *     breadcrumb
 *     identity header         full width
 *     .grid-panels            two columns above 899px, one below
 *       left  : pathway, savings group, linkages
 *       right : finance, household, case
 *
 * .grid-panels already collapses to one column at max-width 899px, so no
 * new media query is needed for the page shell.
 */
export function BeneficiaryProfilePage({
  data,
  onEdit,
  onLogContact,
  onPrint,
}: {
  data: BeneficiaryDetail;
  onEdit: (field?: string) => void;
  onLogContact: () => void;
  onPrint: () => void;
}) {
  const { identity, household, pathway, savings_group, finance, linkages, permissions } = data;
  const active = linkages.filter((l) => l.blocked_reason === null);
  const blocked = linkages.filter((l) => l.blocked_reason !== null);

  return (
    <div className="page stack">
      <nav className="t-meta" aria-label="Breadcrumb">
        <a href="/wlt/beneficiaries">Beneficiary registry</a>
        {identity.kebele && <> &rsaquo; <a href={`/wlt/kebeles/${identity.kebele.id}`}>{identity.kebele.name}</a></>}
        {" "}&rsaquo; <span style={{ color: "var(--ink-900)", fontWeight: 600 }}>{identity.full_name}</span>
      </nav>

      <BeneficiaryIdentityHeader
        identity={identity}
        householdDependants={household.dependants_count}
        canEdit={permissions.can_edit}
        onEdit={onEdit}
        onLogContact={onLogContact}
        onPrint={onPrint}
      />

      <div className="grid-panels">
        <div className="stack">
          <PathwayStageList
            stages={pathway.stages}
            completeCount={pathway.complete_count}
            totalCount={pathway.total_count}
          />

          {savings_group && (
            <section className="card" aria-labelledby="group-heading">
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "var(--s3)", marginBottom: "var(--s3)" }}>
                <div className="t-caps" id="group-heading">Savings group</div>
                <span className="chip" style={{ background: "var(--green-100)", borderColor: "var(--green-border)", color: "var(--green-ink)" }}>
                  {savings_group.status}
                </span>
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: "var(--s3)", marginBottom: "var(--s4)" }}>
                <GroupAvatar url={savings_group.logo_url} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="t-body-strong" style={{ fontSize: 15 }}>{savings_group.name}</div>
                  <div className="t-meta">
                    {savings_group.phase_label} · {savings_group.member_count} members
                  </div>
                </div>
                <a className="btn btn--sm" href={`/wlt/groups/${savings_group.id}`}>Open group</a>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: "var(--s4)", paddingTop: "var(--s3)", borderTop: "1px solid var(--line-soft)" }}>
                <Pair label="She joined" value={formatDate(savings_group.joined_on)} />
                <Pair label="Facilitator" value={savings_group.facilitator_name} />
                <Pair
                  label="Attendance"
                  value={
                    savings_group.meetings_held
                      ? `${savings_group.meetings_attended} of ${savings_group.meetings_held} meetings`
                      : null
                  }
                />
              </div>
            </section>
          )}

          <section className="card" aria-labelledby="linkage-heading">
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "var(--s3)", marginBottom: "var(--s3)" }}>
              <div className="t-caps" id="linkage-heading">Linkages through her group</div>
              <a className="btn btn--sm" href={`/wlt/groups/${savings_group?.id}/linkages`}>Open linkages</a>
            </div>
            <div className="stack" style={{ gap: "var(--s2)" }}>
              {active.map((l) => (
                <div className="linkage" key={l.id}>
                  <span className="linkage__dot" aria-hidden="true" />
                  <div className="linkage__body">
                    <div className="t-body-strong" style={{ fontSize: 14 }}>{l.type_label}</div>
                    <div className="t-meta">{l.partner_name} · since {formatDate(l.active_since)}</div>
                  </div>
                  <span style={{ fontSize: 12, fontWeight: 600, color: "var(--green-ink)" }}>Active</span>
                </div>
              ))}
              {blocked.map((l) => (
                <div className="linkage linkage--pending" key={l.id}>
                  <span className="linkage__dot" aria-hidden="true" />
                  <div className="linkage__body">
                    <div className="t-body-strong" style={{ fontSize: 14, color: "var(--ink-600)" }}>{l.type_label}</div>
                    <div className="t-meta">{l.blocked_reason}</div>
                  </div>
                  <span style={{ fontSize: 12, fontWeight: 600, color: "var(--gold-700)" }}>Not yet</span>
                </div>
              ))}
            </div>
          </section>
        </div>

        <div className="stack">
          <SavingsSummaryCard finance={finance} />

          <section className="card" aria-labelledby="household-heading">
            <div className="t-caps" id="household-heading" style={{ marginBottom: "var(--s3)" }}>
              Household and vulnerability
            </div>
            <Row label="Head of household" value={boolLabel(household.is_head_of_household)} />
            <Row label="Marital status" value={titleCase(household.marital_status)} />
            <Row
              label="Dependants"
              value={
                household.dependants_count === null
                  ? null
                  : `${household.dependants_count}${household.dependants_under_5 ? ` (${household.dependants_under_5} under 5)` : ""}`
              }
            />
            <Row label="Disability" value={household.disability_type === "none" ? "None recorded" : titleCase(household.disability_type)} />
            <Row
              label="Education"
              value={
                household.education_level === null
                  ? null
                  : `${titleCase(household.education_level)}${household.education_grade ? `, grade ${household.education_grade}` : ""}`
              }
              last
            />
          </section>

          <section className="card" aria-labelledby="case-heading">
            <div className="t-caps" id="case-heading" style={{ marginBottom: "var(--s3)" }}>Case and activity</div>
            <Row label="Development agent" value={data.case.development_agent?.name ?? null} />
            <Row label="Last contact" value={formatDateWithAgo(data.case.last_contact_on)} />
            <Row
              label="Enterprise"
              value={data.case.enterprise ? `${data.case.enterprise.name} · ${data.case.enterprise.status}` : null}
            />
            <div className="indicator-row" style={{ padding: "9px 0" }}>
              <span style={{ color: "var(--ink-600)" }}>Grievances</span>
              {data.case.open_grievance_count > 0 ? (
                <span className="chip" style={{ background: "var(--gold-100)", borderColor: "var(--gold-border)", color: "var(--gold-700)" }}>
                  {data.case.open_grievance_count} open
                </span>
              ) : (
                <span style={{ fontWeight: 600 }}>None</span>
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value, last }: { label: string; value: string | null; last?: boolean }) {
  return (
    <div
      className="indicator-row"
      style={{ padding: "9px 0", borderBottom: last ? "none" : "1px solid var(--line-soft)" }}
    >
      <span style={{ color: "var(--ink-600)" }}>{label}</span>
      <span style={{ fontWeight: 600, color: value === null ? "var(--ink-400)" : undefined }}>
        {value ?? "Not recorded"}
      </span>
    </div>
  );
}

function Pair({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <div className="t-meta">{label}</div>
      <div style={{ fontSize: 14, fontWeight: 600 }}>{value ?? "—"}</div>
    </div>
  );
}

function GroupAvatar({ url }: { url: string | null }) {
  if (url) {
    return (
      <img src={url} alt="" width={40} height={40}
           style={{ borderRadius: "var(--r-button)", border: "1px solid var(--line)", objectFit: "cover" }} />
    );
  }
  // Placeholder tile. Never render a broken <img> with visible alt text.
  return (
    <div style={{ width: 40, height: 40, flex: "none", borderRadius: "var(--r-button)",
                  background: "var(--fill-muted)", border: "1px solid var(--line)",
                  display: "flex", alignItems: "center", justifyContent: "center" }}
         aria-hidden="true">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--ink-400)"
           strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="9" cy="8" r="3" />
        <circle cx="16.5" cy="9.5" r="2.2" />
        <path d="M3.5 19c0-3 2.5-5 5.5-5s5.5 2 5.5 5" />
        <path d="M15 14.2c2.6.2 4.5 2.1 4.5 4.8" />
      </svg>
    </div>
  );
}

const boolLabel = (v: boolean | null) => (v === null ? null : v ? "Yes" : "No");
const titleCase = (v: string | null) =>
  v === null ? null : v.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
