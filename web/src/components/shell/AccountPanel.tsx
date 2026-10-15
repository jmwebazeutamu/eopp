import type { CurrentUser } from "../../api/types";
import { useLang } from "../../i18n/LanguageContext";
import LanguageSwitch from "./LanguageSwitch";

/**
 * Who is signed in and what belongs to them: language, manual, profile,
 * sign-out. One definition, drawn by the desktop account menu and by the phone
 * drawer, so the two cannot offer different things.
 */
export default function AccountPanel({
  user,
  onSignOut,
  onOpenProfile,
  onNavigate,
}: {
  user: CurrentUser;
  onSignOut: () => void;
  onOpenProfile?: () => void;
  /** Called before any action that leaves the panel, so the caller can close it. */
  onNavigate?: () => void;
}) {
  const { t } = useLang();
  return (
    <div className="account-panel">
      <div style={{ fontWeight: 700 }}>{user.full_name}</div>
      <div className="t-meta">{user.role_display}</div>
      <div className="t-meta" style={{ marginTop: 6 }}>
        {t("shell.woreda")}: {user.woreda_assignment?.length ? user.woreda_assignment.join(", ") : t("shell.allWoredas")}
      </div>

      <div className="account-group">
        <div className="t-meta" style={{ marginBottom: 6 }}>
          {t("shell.language")}
        </div>
        <LanguageSwitch />
      </div>

      {/* A real link to a real file, not a route: the manual has to survive the
          app not loading. New tab, so a half-finished form is not thrown away. */}
      <a className="account-action" href="/manual.html" target="_blank" rel="noreferrer" onClick={onNavigate}>
        {t("nav.manual")}
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <span className="sr-only">{t("shell.opensNewTab")}</span>
      </a>

      <button
        type="button"
        className="account-action"
        onClick={() => {
          onNavigate?.();
          onOpenProfile?.();
        }}
      >
        {t("profile.open")}
      </button>

      <button type="button" className="account-action" onClick={onSignOut}>
        {t("nav.signOut")}
      </button>
    </div>
  );
}
