import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import { api } from "../api/client";
import type { AlertSummary } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { useLang } from "../i18n/LanguageContext";
import Footer from "./shell/Footer";
import Header from "./shell/Header";
import { ScopeProvider } from "./shell/ScopeContext";
import MobileNav from "./shell/MobileNav";
import TopNav from "./shell/TopNav";
import ProfileModal from "./ProfileModal";
import UserMenu from "./shell/UserMenu";
import { buildNav } from "./shell/navModel";

const DevRoleSwitcher = import.meta.env.DEV ? lazy(() => import("../dev/RoleSwitcher")) : null;

/**
 * The application shell.
 *
 * Header, then horizontal primary navigation, then the active module's
 * secondary navigation, then the page. There is no side rail: the working area
 * takes the full width. Below the 780px structural breakpoint the same
 * navigation model opens as a drawer from a labelled Menu button.
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
  if (!user) return <Navigate to="/" replace />;

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

      <Header
        isPhone={isPhone}
        menu={
          <MobileNav
            user={user}
            sections={sections}
            pathname={location.pathname}
            onSignOut={logout}
            onOpenProfile={() => setProfileOpen(true)}
          />
        }
        account={<UserMenu user={user} onSignOut={logout} onOpenProfile={() => setProfileOpen(true)} />}
      />
      {!isPhone && <TopNav user={user} sections={sections} pathname={location.pathname} />}

      <main id="main" tabIndex={-1} style={{ flex: 1, minWidth: 0, minHeight: 0, overflowY: "auto", display: "flex", flexDirection: "column", paddingBottom: import.meta.env.DEV ? 72 : 0 }}>
        <div style={{ flex: 1 }}>
          <Outlet />
        </div>
        <Footer />
      </main>
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
