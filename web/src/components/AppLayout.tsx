import { useCallback, useEffect, useState } from "react";
import { Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";

import { api } from "../api/client";
import type { AlertSummary } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { useLang } from "../i18n/LanguageContext";
import { Icon } from "./ui";
import Header from "./shell/Header";
import { ScopeProvider } from "./shell/ScopeContext";
import Sidebar from "./shell/Sidebar";
import UserMenu from "./shell/UserMenu";
import { buildNav, isActivePath } from "./shell/navModel";
import { usePreference } from "./shell/preferences";

/**
 * The application shell — the handoff's navigation model.
 *
 * Laptop: a --green-700 rail, 240px expanded or 64px icon-only, grouped into
 * Work and Directory with a footer block naming the signed-in user.
 * Phone: a 56px bottom tab bar, icon-only, sticky *inside* the main column
 * rather than position:fixed — fixed escapes a constrained shell and lands in
 * the wrong place inside an embedded frame.
 *
 * The single 780px breakpoint decides which one renders.
 */

const BADGE_POLL_MS = 120_000;
const BREAKPOINT = 780;

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
  const { t } = useLang();
  const navigate = useNavigate();
  const location = useLocation();
  const isPhone = useIsPhone();
  const [openAlerts, setOpenAlerts] = useState(0);
  // Per user, not per browser: these are shared office machines.
  const [railCollapsed, setRailCollapsed] = usePreference("rail.collapsed", user?.id, false);

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

  const sections = buildNav(user, { openAlerts });
  // The bottom bar has no room for section headings; item 7 reduces this list.
  const flatNav = sections.flatMap((section) => section.items);
  const active = (path: string) => isActivePath(path, location.pathname);

  return (
    // The shell owns the viewport and does not scroll; `main` is the scroll
    // container. Previously the document scrolled, which made the rail either
    // stretch to the height of the page (2,203px on a full case list) or, once
    // it was pinned to 100vh, hang 60px past the bottom of the window because
    // it starts *below* the header — clipping the only sign-out button.
    <ScopeProvider user={user}>
    <div style={{ height: "100vh", overflow: "hidden", display: "flex", flexDirection: "column", background: "var(--paper)" }}>
      <Header />

      <div style={{ display: "flex", flex: 1, minHeight: 0 }}>
        {!isPhone && (
          <Sidebar
            user={user}
            sections={sections}
            pathname={location.pathname}
            collapsed={railCollapsed}
            onToggleCollapse={() => setRailCollapsed(!railCollapsed)}
            footer={
              <div style={{ paddingTop: 10, borderTop: "1px solid rgba(255,255,255,.15)" }}>
                <UserMenu user={user} collapsed={railCollapsed} onSignOut={logout} />
              </div>
            }
          />
        )}

        <main style={{ flex: 1, minWidth: 0, minHeight: 0, overflowY: "auto", display: "flex", flexDirection: "column" }}>
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
              {flatNav.map((entry) => (
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
    </ScopeProvider>
  );
}
