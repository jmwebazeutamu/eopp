import type { BeneficiaryIdentity as Identity } from "../../api/types";
import { CapsLabel } from "../../components/ui";
import { VERIFICATION_TONE } from "../../design/wltStatus";
import { useLang } from "../../i18n/LanguageContext";
import { factsFor, identifiersFor, initialsFor, missingCount } from "./beneficiaryFacts";

/**
 * Who this woman is, before the page says anything about programme status.
 *
 * The screen it replaces put her name in a page header and went straight to
 * gate conditions. There was no ID, no age, no phone and no place anywhere on
 * it — so a development agent standing in a kebele had no way to confirm that
 * the record she had open was the person in front of her, which is the first
 * thing anybody does with a profile and the last thing this page supported.
 *
 * Three states, and the middle one is the reason the block exists:
 *
 * - **complete** — the verification chip, and nothing else to say.
 * - **details missing** — a gold chip counting the blank header fields. The
 *   register holds partial records by design and the ELS extract does not carry
 *   every column, so this is not an error; it is work somebody has to do, and a
 *   row of silent dashes does not say so.
 * - **exited** is not rendered here. `BeneficiaryProfile` has no exit — a
 *   *membership* closes, the woman stays on the register — so a muted "Exited"
 *   card would be describing a state the schema cannot hold. Her group card
 *   carries the membership.
 *
 * The design pairs each blank field with a gold **Add** link that opens the
 * edit form on that field. There is no beneficiary edit form: `POST
 * /wlt/profiles/register/` creates and nothing amends. A control that opens
 * nothing is worse than an honest blank, so the count chip carries the message
 * and the cells read "Not recorded" until the form exists.
 */
export default function BeneficiaryIdentityCard({ identity }: { identity: Identity }) {
  const { t } = useLang();
  const facts = factsFor(identity);
  const missing = missingCount(identity);
  const tone = VERIFICATION_TONE[identity.verification_status];

  return (
    <section className="card record-identity" aria-labelledby="identity-name">
      <div className="record-identity__head">
        <div className="record-identity__avatar" aria-hidden>
          {initialsFor(identity.full_name)}
        </div>

        <div className="record-identity__body">
          <div className="chip-row">
            <h1 id="identity-name" className="record-identity__name">
              {identity.full_name}
            </h1>
            <span className="chip" style={{ color: tone.fg, background: tone.bg, borderColor: tone.bd }}>
              <span className="chip__mark" aria-hidden>
                {tone.mark}
              </span>
              {identity.verification_status_display}
            </span>
            {/* Only when there is something to count. A gold "0 details
                missing" chip is a warning about a complete record. */}
            {missing > 0 && (
              <span
                className="chip"
                style={{ color: MISSING_TONE.fg, background: MISSING_TONE.bg, borderColor: MISSING_TONE.bd }}
                title={t("wlt.detailsMissingHelp")}
              >
                <span className="chip__mark" aria-hidden>
                  {MISSING_TONE.mark}
                </span>
                {t("wlt.detailsMissing", { count: missing })}
              </span>
            )}
          </div>

          <p className="record-identity__ids tabular">
            {identifiersFor(identity).map((row, index) => (
              <span key={row.code}>
                {index > 0 && <span className="record-identity__sep" aria-hidden>/</span>}
                <span className="t-caps record-identity__id-label">{t(ID_LABEL[row.code])}</span>{" "}
                {row.value ?? <span className="t-meta">{t("wlt.notRecorded")}</span>}
              </span>
            ))}
          </p>

          <dl className="record-facts">
            {facts.map((fact) => (
              <div key={fact.code}>
                <dt>
                  <CapsLabel>{t(fact.labelKey)}</CapsLabel>
                </dt>
                <dd className={fact.code === "phone_number" || fact.code === "age" ? "tabular" : undefined}>
                  {fact.value ?? <span className="t-meta">{t("wlt.notRecorded")}</span>}
                  {fact.value && fact.note && <span className="t-meta"> / {fact.note}</span>}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
    </section>
  );
}

/** Gold, like every other "somebody has to do this" tone in the module. Never
 *  red: a partial record is the register working as specified, not a fault. */
const MISSING_TONE = {
  fg: "var(--gold-700)",
  bg: "var(--gold-100)",
  bd: "var(--gold-border)",
  mark: "◇",
} as const;

/** Written out rather than built from the code: a template-literal key cannot
 *  be checked against the string table, which is the point of having one. */
const ID_LABEL = {
  national_id: "wlt.idLabel",
  psnp_client_id: "wlt.psnpClientLabel",
  registered_on: "wlt.registeredLabel",
} as const;
