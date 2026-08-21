import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import { api } from "../api/client";
import type { AlertSummary } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { useLang } from "../i18n/LanguageContext";
import Header from "./shell/Header";
import { ScopeProvider } from "./shell/ScopeContext";
import MobileTabBar from "./shell/MobileTabBar";
import Sidebar from "./shell/Sidebar";
import ProfileModal from "./ProfileModal";
import UserMenu from "./shell/UserMenu";
import { buildNav } from "./shell/navModel";
import { usePreference } from "./shell/preferences";

const DevRoleSwitcher = import.meta.env.DEV ? lazy(() => import("../dev/RoleSwitcher")) : null;

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
  const location = useLocation();
  const { t } = useLang();
  const isPhone = useIsPhone();
  const [openAlerts, setOpenAlerts] = useState(0);
  const [profileOpen, setProfileOpen] = useState(false);
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

  return (
    // The shell owns the viewport and does not scroll; `main` is the scroll
    // container. Previously the document scrolled, which made the rail either
    // stretch to the height of the page (2,203px on a full case list) or, once
    // it was pinned to 100vh, hang 60px past the bottom of the window because
    // it starts *below* the header — clipping the only sign-out button.
    <ScopeProvider user={user}>
    <div style={{ height: "100vh", overflow: "hidden", display: "flex", flexDirection: "column", background: "var(--paper)" }}>
      {/* Ten tab stops — header search, scope, rail collapse, six nav items,
          account — sat between arriving and the page content, on every
          navigation. Visible only on focus. */}
      <a className="skip-link" href="#main">
        {t("shell.skipToContent")}
      </a>

      {isPhone && <Header isPhone />}

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
                <UserMenu
                  user={user}
                  collapsed={railCollapsed}
                  onSignOut={logout}
                  onOpenProfile={() => setProfileOpen(true)}
                />
              </div>
            }
          />
        )}

        <main id="main" tabIndex={-1} style={{ flex: 1, minWidth: 0, minHeight: 0, overflowY: "auto", display: "flex", flexDirection: "column", paddingBottom: import.meta.env.DEV ? 72 : 0 }}>
          <div style={{ flex: 1 }}>
            <Outlet />
          </div>

          {isPhone && (
            <MobileTabBar user={user} sections={sections} pathname={location.pathname} onSignOut={logout} />
          )}
        </main>
      </div>
    </div>
      <ProfileModal open={profileOpen} onClose={() => setProfileOpen(false)} />
      {DevRoleSwitcher && (
        <Suspense fallback={null}>
          <DevRoleSwitcher />
        </Suspense>
      )}
    </ScopeProvider>
  );
}
