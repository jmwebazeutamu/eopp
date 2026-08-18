import { Modal } from "antd";

import type { ManagedUser } from "../api/types";
import { useLang } from "../i18n/LanguageContext";
import { Button, CapsLabel, Field, MutedChip } from "./ui";

/**
 * An account, read first.
 *
 * The same rule as the other registries, and it matters more here: the edit
 * form carries a password field and the role that decides what this person can
 * see. Opening someone's account to check their caseload should not put a
 * finger next to either.
 */

interface Props {
  user: ManagedUser | null;
  onClose: () => void;
  onEdit: (user: ManagedUser) => void;
}

const STATUS_TONE: Record<ManagedUser["account_status"], { fg: string; bg: string }> = {
  ACTIVE: { fg: "var(--green-ink)", bg: "var(--green-100)" },
  SUSPENDED: { fg: "var(--terra-700)", bg: "var(--terra-100)" },
  INACTIVE: { fg: "var(--ink-600)", bg: "var(--fill-muted-2)" },
};

export default function UserDetailModal({ user, onClose, onEdit }: Props) {
  const { t } = useLang();
  if (!user) return null;

  const tone = STATUS_TONE[user.account_status];

  return (
    <Modal
      open
      onCancel={onClose}
      title={user.full_name}
      width={560}
      footer={
        <Button variant="primary" onClick={() => onEdit(user)}>
          {t("users.edit")}
        </Button>
      }
    >
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", marginBottom: 12 }}>
        <MutedChip>{user.role_display}</MutedChip>
        <span className="chip" style={{ color: tone.fg, background: tone.bg, borderColor: "transparent" }}>
          {user.account_status}
        </span>
      </div>

      <div className="grid-pairs">
        <Field label={t("users.username")}>{user.username}</Field>
        <Field label={t("profile.workEmail")}>{user.work_email || t("common.none")}</Field>
        <Field label={t("profile.personalEmail")}>{user.personal_email || t("common.none")}</Field>
        <Field label={t("profile.workPhone")}>{user.work_phone || t("common.none")}</Field>
        <Field label={t("profile.personalPhone")}>{user.personal_phone || t("common.none")}</Field>
        {user.role === "CASE_MANAGER" && (
          // §11 sets a caseload ceiling of 50; an administrator reassigning work
          // needs the current load in front of them.
          <Field label={t("users.caseload")}>
            <span className="tabular">{user.caseload_count}</span>
          </Field>
        )}
        <Field label={t("users.lastSeen")}>
          {user.last_login ? new Date(user.last_login).toLocaleString("en-GB") : t("users.neverSignedIn")}
        </Field>
      </div>

      <div className="card__rule" style={{ margin: "14px 0" }} />

      {/* §7 scoping: what this account can see is a property of the account, so
          it belongs on the account's record rather than only in the edit form. */}
      <CapsLabel>{t("users.scope")}</CapsLabel>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 6 }}>
        {user.partner_name ? (
          <MutedChip style={{ fontSize: 12 }}>{user.partner_name}</MutedChip>
        ) : user.woreda_assignment.length ? (
          user.woreda_assignment.map((woreda) => (
            <MutedChip key={woreda} style={{ fontSize: 12 }}>
              {woreda}
            </MutedChip>
          ))
        ) : (
          <span className="t-meta">{t("users.allWoredas")}</span>
        )}
      </div>

      <div className="t-meta" style={{ marginTop: 10 }}>
        {t("users.joined", { date: new Date(user.date_joined).toLocaleDateString("en-GB") })}
      </div>
    </Modal>
  );
}
