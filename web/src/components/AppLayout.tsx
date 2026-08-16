import { useCallback, useEffect, useState } from "react";
import { Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";

import { api } from "../api/client";
import type { AlertSummary } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { LANGUAGES, useLang } from "../i18n/LanguageContext";
import type { StringKey } from "../i18n/strings";
import { CountBadge, Icon, ICON_PATHS, LogoMark } from "./ui";

/**
 * The application shell — the handoff's navigation model.
 *
 * Laptop: a 236px --green-700 rail with 44px items, the active one filled
 * --green-500, and a footer block naming the signed-in user and their caseload.
 * Phone: a 56px bottom tab bar, icon-only, sticky *inside* the main column
 * rather than position:fixed — fixed escapes a constrained shell and lands in
 * the wrong place inside an embedded frame.
 *
 * The single 780px breakpoint decides which one renders.
 */

const BADGE_POLL_MS = 120_000;
const BREAKPOINT = 780;

interface NavEntry {
  path: string;
  labelKey: StringKey;
  icon: string;
  badge?: number;
}

function useIsPhone() {
  const [isPhone, setIsPhone] = useState(() => window.innerWidth < BREAKPOINT);
  useEffect(() => {
    const query = window.matchMedia(`(max-width: ${BREAKPOINT - 1}px)`);
    const update = () => setIsPhone(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  return isPhone;
}

export default function AppLayout() {
  const { user, loading, logout } = useAuth();
  const { lang, setLang, t } = useLang();
  const navigate = useNavigate();
  const location = useLocation();
  const isPhone = useIsPhone();
  const [openAlerts, setOpenAlerts] = useState(0);

  const refreshBadge = useCallback(async () => {
    // The alert endpoints are gated on case access, so a role with none would
    // only 403 here. Skip rather than spam the console.
    if (!user || user.access.case_scope === "NONE") return;
    try {
      const response = await api.get<AlertSummary>("/alerts/summary/");
      setOpenAlerts(response.data.assigned_to_me);
    } catch {
      // A badge is not worth surfacing an error for.
    }
  }, [user]);

  useEffect(() => {
    void refreshBadge();
    // Alerts are raised by scheduled jobs rather than by anything the user did,
    // so the count has to be pulled; nothing in this tab will announce it.
    const timer = setInterval(refreshBadge, BADGE_POLL_MS);
    return () => clearInterval(timer);
  }, [refreshBadge, location.pathname]);

  if (loading) return null;
  if (!user) return <Navigate to="/login" replace />;

  // Nav follows the access matrix, not the role: the API is the authority, and
  // hiding an item only avoids a screen that would 403 or come back empty.
  const nav: NavEntry[] = [
    ...(user.access.case_scope === "NONE" ? [] : [{ path: "/cases", labelKey: "nav.cases" as const, icon: ICON_PATHS.cases }]),
    ...(user.access.referral_scope === "NONE"
      ? []
      : [{ path: "/referrals", labelKey: "nav.referrals" as const, icon: ICON_PATHS.queue }]),
    ...(user.access.case_scope === "NONE"
      ? []
      : [{ path: "/alerts", labelKey: "nav.alerts" as const, icon: ICON_PATHS.alerts, badge: openAlerts }]),
    ...(user.access.case_scope === "NONE"
      ? []
      : [{ path: "/youth", labelKey: "nav.registry" as const, icon: ICON_PATHS.registry }]),
    { path: "/partners", labelKey: "nav.partners", icon: ICON_PATHS.partners },
    ...(user.role === "SYSTEM_ADMIN" ? [{ path: "/users", labelKey: "nav.users" as const, icon: ICON_PATHS.users }] : []),
  ];

  const active = (path: string) => location.pathname.startsWith(path);

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column", background: "var(--paper)" }}>
      {/* Utility bar */}
      <header
        style={{
          background: "var(--green-900)",
          color: "var(--on-dark)",
          padding: "8px 16px",
          minHeight: 60,
          display: "flex",
          alignItems: "center",
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        {/* Sentence case rather than uppercase: at this length, caps plus the
            0.06em tracking wraps to two lines on a 360px screen. */}
        <span style={{ fontWeight: 700, fontSize: 18, letterSpacing: "-0.01em" }}>{t("app.name")}</span>
        <span style={{ color: "var(--on-dark-3)", fontSize: 13 }}>
          {t("shell.woreda")}: {user.woreda_assignment?.join(", ") || "—"}
        </span>

        <div style={{ marginLeft: "auto", display: "flex", gap: 4 }}>
          {LANGUAGES.map((entry) => (
            <button
              key={entry.code}
              type="button"
              onClick={() => setLang(entry.code)}
              aria-pressed={lang === entry.code}
              style={{
                minHeight: 32,
                padding: "0 12px",
                borderRadius: "var(--r-button)",
                border: "1px solid rgba(255,255,255,.25)",
                background: lang === entry.code ? "var(--surface)" : "transparent",
                color: lang === entry.code ? "var(--ink-900)" : "var(--on-dark-2)",
                fontWeight: 600,
                fontSize: 13,
                fontFamily: "var(--font-body)",
                cursor: "pointer",
              }}
            >
              {entry.label}
            </button>
          ))}
        </div>
      </header>

      <div style={{ display: "flex", flex: 1, minHeight: 0 }}>
        {!isPhone && (
          <nav
            style={{
              width: "var(--rail-width)",
              flexShrink: 0,
              background: "var(--green-700)",
              color: "var(--on-dark)",
              display: "flex",
              flexDirection: "column",
              padding: "16px 12px",
              gap: 4,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "0 8px 16px" }}>
              <LogoMark />
              <div style={{ lineHeight: 1.2 }}>
                <div style={{ fontWeight: 700, fontSize: 15 }}>Case</div>
                <div style={{ color: "var(--on-dark-2)", fontSize: 13 }}>{t("app.subtitle")}</div>
              </div>
            </div>

            {nav.map((entry) => (
              <button
                key={entry.path}
                type="button"
                onClick={() => navigate(entry.path)}
                style={{
                  minHeight: 44,
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  padding: "0 12px",
                  borderRadius: "var(--r-button)",
                  border: "none",
                  background: active(entry.path) ? "var(--green-500)" : "transparent",
                  color: "var(--on-dark)",
                  font: "inherit",
                  fontSize: 15,
                  fontWeight: active(entry.path) ? 600 : 400,
                  fontFamily: "var(--font-body)",
                  cursor: "pointer",
                  textAlign: "left",
                  width: "100%",
                }}
              >
                <Icon path={entry.icon} />
                <span style={{ flex: 1 }}>{t(entry.labelKey)}</span>
                {entry.badge ? <CountBadge>{entry.badge}</CountBadge> : null}
              </button>
            ))}

            <div style={{ marginTop: "auto", paddingTop: 16, borderTop: "1px solid rgba(255,255,255,.15)" }}>
              <div style={{ fontWeight: 600, fontSize: 14 }}>{user.full_name}</div>
              <div style={{ color: "var(--on-dark-2)", fontSize: 13 }}>{user.role_display}</div>
              <button
                type="button"
                onClick={logout}
                style={{
                  marginTop: 8,
                  minHeight: 36,
                  width: "100%",
                  borderRadius: "var(--r-button)",
                  border: "1px solid rgba(255,255,255,.25)",
                  background: "transparent",
                  color: "var(--on-dark-2)",
                  font: "inherit",
                  fontSize: 13,
                  fontFamily: "var(--font-body)",
                  cursor: "pointer",
                }}
              >
                {t("nav.signOut")}
              </button>
            </div>
          </nav>
        )}

        <main style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
          <div style={{ flex: 1 }}>
            <Outlet />
          </div>

          {isPhone && (
            <nav
              style={{
                position: "sticky",
                bottom: 0,
                height: "var(--tabbar-height)",
                background: "var(--green-700)",
                display: "flex",
                alignItems: "stretch",
              }}
            >
              {nav.map((entry) => (
                <button
                  key={entry.path}
                  type="button"
                  onClick={() => navigate(entry.path)}
                  aria-label={t(entry.labelKey)}
                  style={{
                    flex: 1,
                    border: "none",
                    background: active(entry.path) ? "var(--green-500)" : "transparent",
                    color: "var(--on-dark)",
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: 2,
                    cursor: "pointer",
                    fontFamily: "var(--font-body)",
                  }}
                >
                  <Icon path={entry.icon} size={20} />
                  <span style={{ fontSize: 9, fontWeight: 600 }}>{t(entry.labelKey)}</span>
                </button>
              ))}
            </nav>
          )}
        </main>
      </div>
    </div>
  );
}
