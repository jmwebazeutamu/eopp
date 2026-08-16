import { Modal } from "antd";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import type { Youth } from "../api/types";
import { useLang } from "../i18n/LanguageContext";
import { Button, CapsLabel, Field, MutedChip, maskPhone } from "./ui";

/**
 * A youth record, read first.
 *
 * Opening a record is not the same as changing it: most visits to this screen
 * are someone checking a phone number or a consent date, and dropping straight
 * into a form invites an accidental edit to a record §9 holds an audit trail
 * over. Editing is a deliberate second step.
 *
 * The phone number stays masked here, as everywhere in the registry. The reveal
 * on the case screen exists because a case manager working one youth has a
 * reason to see it; browsing the registry is not that reason.
 */

interface Props {
  youth: Youth | null;
  canEdit: boolean;
  onClose: () => void;
  onEdit: (youth: Youth) => void;
}

export default function YouthDetailModal({ youth, canEdit, onClose, onEdit }: Props) {
  const { t } = useLang();
  const navigate = useNavigate();
  const [revealPhone, setRevealPhone] = useState(false);

  if (!youth) return null;

  return (
    <Modal
      open
      onCancel={() => {
        setRevealPhone(false);
        onClose();
      }}
      title={youth.full_name}
      width={640}
      footer={
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "flex-end" }}>
          {youth.open_case_id && (
            <Button onClick={() => navigate(`/cases/${youth.open_case_id}`)}>{t("registry.goToCase")}</Button>
          )}
          {canEdit && (
            <Button variant="primary" onClick={() => onEdit(youth)}>
              {t("registry.edit")}
            </Button>
          )}
        </div>
      }
    >
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", marginBottom: 12 }}>
        {youth.has_open_case ? (
          <span
            className="chip"
            style={{ color: "var(--green-ink)", background: "var(--green-100)", borderColor: "var(--green-border)" }}
          >
            {t("registry.openCase")}
          </span>
        ) : (
          <MutedChip>{t("registry.noCase")}</MutedChip>
        )}
        {!youth.is_age_eligible && (
          <span
            className="chip"
            style={{ color: "var(--terra-700)", background: "var(--terra-100)", borderColor: "var(--terra-border)" }}
            // §11 has not confirmed the band, so this is a flag, not a verdict.
            title="Outside the configured youth age band — eligibility needs confirmation."
          >
            ▲ {t("registry.outsideAgeBand")}
          </span>
        )}
      </div>

      <div className="grid-pairs">
        <Field label={t("registry.col.id")}>{youth.national_or_kebele_id || t("common.none")}</Field>
        <Field label={t("case.age")}>{youth.age}</Field>
        <Field label={t("case.sex")}>{youth.sex_display ?? youth.sex}</Field>
        <Field label={t("case.dob")}>{youth.date_of_birth}</Field>
        <Field label={t("cases.col.woreda")}>
          {youth.woreda} · {youth.kebele}
        </Field>
        <Field label={t("registry.region")}>
          {youth.region} · {youth.zone}
        </Field>
      </div>

      <div className="card__rule" style={{ margin: "14px 0" }} />

      <div className="grid-pairs">
        <Field label={t("case.phone")}>
          <span className="tabular">
            {youth.phone_number
              ? revealPhone
                ? youth.phone_number
                : maskPhone(youth.phone_number)
              : t("common.none")}
          </span>
          {youth.phone_number && (
            <Button size="sm" style={{ marginTop: 6 }} onClick={() => setRevealPhone(!revealPhone)}>
              {revealPhone ? t("case.hide") : t("case.reveal")}
            </Button>
          )}
        </Field>
        <Field label={t("registry.household")}>{youth.household_id || t("common.none")}</Field>
        <Field label={t("registry.psnp")}>{youth.psnp_status || t("common.none")}</Field>
        <Field label={t("registry.education")}>{youth.education_level || t("common.none")}</Field>
        <Field label={t("registry.disability")}>{youth.disability_status || t("common.none")}</Field>
      </div>

      <div className="card__rule" style={{ margin: "14px 0" }} />

      {/* §9 makes consent the basis for holding the record at all, so it is
          stated plainly rather than buried among the demographics. */}
      <CapsLabel>{t("registry.consent")}</CapsLabel>
      <div style={{ marginTop: 4 }}>
        {youth.consent_given
          ? t("case.consent", { date: youth.consent_date ?? "—" })
          : t("registry.noConsentRecorded")}
      </div>
      <div className="t-meta" style={{ marginTop: 6 }}>
        {t("registry.registeredBy", {
          date: youth.registration_date,
          name: youth.registering_worker_name || "—",
        })}
      </div>
    </Modal>
  );
}
