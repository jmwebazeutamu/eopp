import type { Identity } from "./types";
import { Fact } from "./Fact";
import { formatDate, formatPhone, initials } from "./format";

interface Props {
  identity: Identity;
  householdDependants: number | null;
  canEdit: boolean;
  onEdit: (field?: string) => void;
  onLogContact: () => void;
  onPrint: () => void;
}

/**
 * The identity block. Sits directly under the breadcrumb, above every
 * other card. It answers "who is this woman" before the page says
 * anything about her programme status.
 *
 * States are driven entirely by `identity.status` and null fields:
 *   active/inactive + no nulls  -> complete
 *   active/inactive + nulls     -> "N details missing" chip, Add controls
 *   exited                      -> muted card, exit reason on the face
 */
export function BeneficiaryIdentityHeader({
  identity,
  householdDependants,
  canEdit,
  onEdit,
  onLogContact,
  onPrint,
}: Props) {
  const exited = identity.status === "exited";
  const missing = identity.missing_field_count;

  return (
    <section className={exited ? "card card--muted" : "card"} aria-labelledby="bene-name">
      <div className="bene-header">
        {identity.photo_url ? (
          <div className="bene-header__avatar">
            <img src={identity.photo_url} alt="" />
          </div>
        ) : canEdit && !exited ? (
          <button
            type="button"
            className="bene-header__avatar bene-header__avatar--empty"
            onClick={() => onEdit("photo")}
          >
            <PersonIcon />
            Add photo
          </button>
        ) : (
          <div
            className={
              exited
                ? "bene-header__avatar bene-header__avatar--muted"
                : "bene-header__avatar"
            }
            aria-hidden="true"
          >
            {initials(identity.full_name)}
          </div>
        )}

        <div className="bene-header__body">
          <div
            style={{
              display: "flex",
              alignItems: "flex-start",
              justifyContent: "space-between",
              gap: "var(--s4)",
              flexWrap: "wrap",
            }}
          >
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <div className="chip-row" style={{ alignItems: "center", gap: 10 }}>
                <h1 id="bene-name" className="bene-header__name">
                  {identity.full_name}
                </h1>
                <StatusChip identity={identity} missing={missing} />
              </div>

              <div className="bene-header__ids">
                <span>ID {identity.reference_code}</span>
                <span className="bene-header__ids-sep">/</span>
                {identity.psnp_client_number ? (
                  <span>PSNP client {identity.psnp_client_number}</span>
                ) : canEdit ? (
                  <button type="button" className="fact__add" style={{ fontSize: 13 }}
                          onClick={() => onEdit("psnp_client_number")}>
                    Add PSNP client number
                  </button>
                ) : (
                  <span>PSNP client &mdash;</span>
                )}
                <span className="bene-header__ids-sep">/</span>
                {exited ? (
                  <span>
                    Left {formatDate(identity.exited_on)}
                    {identity.exit_reason ? ` · ${identity.exit_reason}` : ""}
                  </span>
                ) : (
                  <span>Registered {formatDate(identity.registered_on)}</span>
                )}
              </div>
            </div>

            {!exited && (
              <div className="bene-header__actions">
                {canEdit && (
                  <button type="button" className="btn btn--sm" onClick={() => onEdit()}>
                    Edit details
                  </button>
                )}
                <button type="button" className="btn btn--sm" onClick={onLogContact}>
                  Record contact
                </button>
                <button type="button" className="btn btn--sm btn--primary" onClick={onPrint}>
                  Print profile
                </button>
              </div>
            )}
          </div>

          <div className="fact-grid">
            <Fact
              label="Age"
              value={identity.age}
              qualifier={
                identity.age === null
                  ? null
                  : identity.age_is_estimated
                    ? "estimated"
                    : identity.date_of_birth
                      ? `b. ${new Date(identity.date_of_birth).getFullYear()}`
                      : null
              }
              numeric
              addLabel="date of birth"
              onAdd={() => onEdit("date_of_birth")}
              canEdit={canEdit}
            />
            <Fact
              label="Phone"
              value={formatPhone(identity.phone)}
              numeric
              addLabel="phone number"
              onAdd={() => onEdit("phone")}
              canEdit={canEdit}
            />
            <Fact
              label="Woreda"
              value={identity.woreda?.name ?? null}
              onAdd={() => onEdit("woreda")}
              canEdit={canEdit}
            />
            <Fact
              label="Kebele"
              value={identity.kebele?.name ?? null}
              onAdd={() => onEdit("kebele")}
              canEdit={canEdit}
            />
            <Fact
              label="Household size"
              value={identity.household_size}
              qualifier={
                householdDependants === null ? null : `/ ${householdDependants} dependants`
              }
              numeric
              addLabel="household size"
              onAdd={() => onEdit("household_size")}
              canEdit={canEdit}
            />
          </div>
        </div>
      </div>
    </section>
  );
}

function StatusChip({ identity, missing }: { identity: Identity; missing: number }) {
  if (identity.status === "exited") {
    return (
      <span className="chip" style={{ background: "var(--fill-muted)", borderColor: "var(--closed-border)", color: "var(--ink-600)" }}>
        Exited
      </span>
    );
  }
  if (missing > 0) {
    return (
      <span className="chip" style={{ background: "var(--gold-100)", borderColor: "var(--gold-border)", color: "var(--gold-700)" }}>
        {missing} detail{missing === 1 ? "" : "s"} missing
      </span>
    );
  }
  return (
    <span className="chip" style={{ background: "var(--green-100)", borderColor: "var(--green-border)", color: "var(--green-ink)" }}>
      <CheckIcon />
      Active
    </span>
  );
}

function CheckIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M4 12.5l5 5L20 6.5" />
    </svg>
  );
}

function PersonIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="9" r="3.2" />
      <path d="M5 20c0-3.6 3.1-6 7-6s7 2.4 7 6" />
    </svg>
  );
}
