import { Modal } from "antd";

import type { MouStatus, Partner } from "../api/types";
import { useLang } from "../i18n/LanguageContext";
import { Button, CapsLabel, Field, MutedChip } from "./ui";

/**
 * A partner record, read first.
 *
 * Same reasoning as the youth registry: opening a record is not the same as
 * changing it. Most visits here are someone checking whether a partner can take
 * a referral today and whether the MOU behind that is signed — neither is a
 * reason to be dropped into a form.
 */

export const MOU_TONE: Record<MouStatus, { fg: string; bg: string; bd: string }> = {
  SIGNED: { fg: "var(--green-ink)", bg: "var(--green-100)", bd: "var(--green-border)" },
  DRAFT: { fg: "var(--gold-700)", bg: "var(--gold-100)", bd: "var(--gold-border)" },
  NONE: { fg: "var(--terra-700)", bg: "var(--terra-100)", bd: "var(--terra-border)" },
  EXPIRED: { fg: "var(--terra-700)", bg: "var(--terra-100)", bd: "var(--terra-border)" },
  TERMINATED: { fg: "var(--ink-600)", bg: "var(--fill-muted-2)", bd: "var(--closed-border)" },
};

interface Props {
  partner: Partner | null;
  canEdit: boolean;
  onClose: () => void;
  onEdit: (partner: Partner) => void;
}

export default function PartnerDetailModal({ partner, canEdit, onClose, onEdit }: Props) {
  const { t } = useLang();
  if (!partner) return null;

  const tone = MOU_TONE[partner.mou_status];

  return (
    <Modal
      open
      onCancel={onClose}
      title={partner.partner_name}
      width={620}
      footer={
        canEdit ? (
          <Button variant="primary" onClick={() => onEdit(partner)}>
            {t("partners.edit")}
          </Button>
        ) : null
      }
    >
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", marginBottom: 12 }}>
        <MutedChip>{partner.partner_type_display}</MutedChip>
        <span className="chip" style={{ color: tone.fg, background: tone.bg, borderColor: tone.bd }}>
          {partner.mou_status_display}
          {partner.mou_date ? ` · ${partner.mou_date}` : ""}
        </span>
        {/* Capacity and paperwork are different questions: a partner can be
            accepting referrals on an unsigned MOU. */}
        <span
          className="chip"
          style={{
            color: partner.can_receive_referrals ? "var(--green-ink)" : "var(--ink-600)",
            background: partner.can_receive_referrals ? "var(--green-100)" : "var(--fill-muted)",
            borderColor: "transparent",
          }}
        >
          {partner.can_receive_referrals ? `● ${t("partners.accepting")}` : `○ ${t("partners.paused")}`}
        </span>
      </div>

      <div className="grid-pairs">
        <Field label={t("partners.contact")}>{partner.contact_name || t("common.none")}</Field>
        <Field label={t("case.phone")}>
          {/* A partner's number is an institutional contact, not personal data,
              so it is not masked the way a youth's is. */}
          <span className="tabular">{partner.phone || t("common.none")}</span>
        </Field>
        <Field label={t("partners.email")}>{partner.email || t("common.none")}</Field>
      </div>

      <div className="card__rule" style={{ margin: "14px 0" }} />

      <CapsLabel>{t("partners.coverage")}</CapsLabel>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 6 }}>
        {partner.woreda_coverage.length ? (
          partner.woreda_coverage.map((woreda) => (
            <MutedChip key={woreda} style={{ fontSize: 12 }}>
              {woreda}
            </MutedChip>
          ))
        ) : (
          <span className="t-meta">{t("partners.noCoverage")}</span>
        )}
      </div>

      {partner.performance_notes && (
        <>
          <div className="card__rule" style={{ margin: "14px 0" }} />
          <CapsLabel>{t("partners.notes")}</CapsLabel>
          <div style={{ marginTop: 4, fontSize: 14 }}>{partner.performance_notes}</div>
        </>
      )}
    </Modal>
  );
}
