import { App as AntApp, ConfigProvider } from "antd";
import { BrowserRouter, Navigate, Route, Routes, useParams } from "react-router-dom";

import AppLayout from "./components/AppLayout";
import type { ReactNode } from "react";

import { AuthProvider, useAuth } from "./auth/AuthContext";
import { LanguageProvider } from "./i18n/LanguageContext";
import { canSeeTier, landingTier } from "./pages/dashboard/tierAccess";
import { canSeeDelivery, landingDelivery } from "./pages/delivery/deliveryAccess";
import TierUnavailablePage from "./pages/dashboard/TierUnavailablePage";
import AlertsPage from "./pages/AlertsPage";
import CaseDetailPage from "./pages/CaseDetailPage";
import CaseListPage from "./pages/CaseListPage";
import DashboardLayout from "./pages/dashboard/DashboardLayout";
import MyWorkPage from "./pages/dashboard/MyWorkPage";
import ProgrammePage from "./pages/dashboard/ProgrammePage";
import ResultsPage from "./pages/dashboard/ResultsPage";
import WoredaPage from "./pages/dashboard/WoredaPage";
import LandingPage from "./pages/landing/LandingPage";
import EnterprisesPage from "./pages/EnterprisesPage";
import FacilitatorHomePage from "./pages/wlt/FacilitatorHomePage";
import WltDashboardPage from "./pages/wlt/WltDashboardPage";
import WltTierUnavailable from "./pages/wlt/WltTierUnavailable";
import { canSeeWltTier, landingWltTier } from "./pages/wlt/wltTiers";
import GrievanceCasePage from "./pages/GrievanceCasePage";
import GrievancesPage from "./pages/GrievancesPage";
import PartnersPage from "./pages/PartnersPage";
import VerificationPage from "./pages/VerificationPage";
import PlacementsPage from "./pages/PlacementsPage";
import TrainingPage from "./pages/TrainingPage";
import BeneficiariesPage from "./pages/wlt/BeneficiariesPage";
import ClaReadinessPage from "./pages/wlt/ClaReadinessPage";
import FederationReadinessPage from "./pages/wlt/FederationReadinessPage";
import GroupReadinessPage from "./pages/wlt/GroupReadinessPage";
import MeetingPage from "./pages/wlt/MeetingPage";
import NotFoundPage from "./pages/NotFoundPage";
import GroupsPage from "./pages/wlt/GroupsPage";
import JourneyPage from "./pages/wlt/JourneyPage";
import LinkagesPage from "./pages/wlt/LinkagesPage";
import LinkageDetailPage from "./pages/wlt/LinkageDetailPage";
import ReferralsPage from "./pages/ReferralsPage";
import UsersPage from "./pages/UsersPage";
import YouthListPage from "./pages/YouthListPage";

/**
 * Where a signed-in user starts.
 *
 * Not everyone starts at Cases. §7 scopes case records and referral records
 * separately, and for a LINKED-scope role — referral partner staff especially —
 * the case list resolves to nothing by design, so landing there shows an empty
 * screen rather than their work. Read off the access matrix rather than the
 * role, so the landing screen follows whatever §7 currently says.
 */
function Home() {
  const { user } = useAuth();
  if (!user) return <Navigate to="/cases" replace />;
  if (user.access.case_scope === "LINKED") return <Navigate to="/referrals" replace />;
  if (user.access.case_scope === "NONE") {
    // A WLT role before anything else. All four carry `case_scope: NONE` — that
    // is how the module boundary is expressed — so the branch below would have
    // sent a facilitator to the user directory, which she also cannot open.
    // Unreachable until now because the old sign-in navigated to /cases itself;
    // making `/` the post-sign-in destination is what exposed it.
    if (user.access.group_scope !== "NONE") return <Navigate to="/wlt/dashboard" replace />;
    // Nothing at all: not the system administrator since the 2026-08-16
    // deviation, but still any role the matrix does not cover.
    return <Navigate to="/users" replace />;
  }
  // A role that reads case records widely but writes none of them is a
  // supervisory one, and the handoff designs the dashboard for exactly them.
  // Case-facing roles keep landing on their caseload, which is their work.
  //
  if (!user.access.case_write) return <Navigate to="/dashboard" replace />;
  return <Navigate to="/cases" replace />;
}

/**
 * The front door.
 *
 * Waits for the auth bootstrap before choosing: `AuthProvider` starts with
 * `loading` true while it exchanges a stored refresh token, and rendering the
 * public page during that window would flash a marketing hero at somebody who
 * is already signed in.
 */
function Root() {
  const { user, loading } = useAuth();
  if (loading) return null;
  return user ? <Home /> : <LandingPage />;
}

/**
 * Which tier a role lands on.
 *
 * The handoff's §1 argument, applied to routing: a case manager opening
 * /dashboard should get their own work, and a donor should get results. Sending
 * everyone to the same tier is how one dashboard ends up serving four
 * audiences badly.
 */
function DashboardHome() {
  const { user } = useAuth();
  const target = landingTier(user);
  // A role with no dashboard is sent to its own work rather than to a tier that
  // would immediately refuse it. Partner staff and trainers land here.
  return <Navigate to={target ? `/dashboard/${target.path}` : "/referrals"} replace />;
}

/**
 * Where `/wlt/dashboard` lands this role.
 *
 * Her own tier, so a facilitator gets her queue and a region officer gets the
 * programme view — the handoff's §1 argument applied to routing. Four small
 * dashboards, not one with role-based hiding.
 */
function WltDashboardHome() {
  const { user } = useAuth();
  const target = landingWltTier(user);
  return <Navigate to={target ? `/wlt/dashboard/${target.path}` : "/wlt/groups"} replace />;
}

/** A WLT tier route, refused with an explanation rather than a redirect. */
function WltTier({ path, children }: { path: string; children: ReactNode }) {
  const { user } = useAuth();
  return canSeeWltTier(user, path) ? <>{children}</> : <WltTierUnavailable />;
}

/** The same guard, reading the tier from the URL rather than from a prop. */
function WltTierRoute() {
  const { tier = "" } = useParams();
  return (
    <WltTier path={tier}>
      <WltDashboardPage />
    </WltTier>
  );
}

/**
 * Where `/delivery` lands this role.
 *
 * Its own first screen, so a trainer gets Training and an employer liaison gets
 * Placements — the same argument `DashboardHome` makes about the tiers. A role
 * with none is sent to its cases rather than to a screen that would refuse it.
 */
function DeliveryHome() {
  const { user } = useAuth();
  const target = landingDelivery(user);
  return <Navigate to={target ? target.path : "/cases"} replace />;
}

/**
 * A delivery route, refused with an explanation rather than a redirect.
 *
 * Same reasoning as the tier guard: bouncing somebody off a link a colleague
 * sent them, silently, reads as a broken link.
 */
function Delivery({ path, children }: { path: string; children: ReactNode }) {
  const { user } = useAuth();
  return canSeeDelivery(user, path) ? <>{children}</> : <TierUnavailablePage />;
}

/**
 * A tier route, refused politely rather than blankly.
 *
 * The guard renders an explanation in place, never a redirect: bouncing someone
 * off a link a colleague sent them, silently, reads as a broken link, and the
 * tier they would be bounced to may redirect in turn.
 */
function Tier({ path, children }: { path: string; children: ReactNode }) {
  const { user } = useAuth();
  return canSeeTier(user, path) ? <>{children}</> : <TierUnavailablePage />;
}

/**
 * Ant Design keeps the behaviour-heavy components — Modal, Select, DatePicker,
 * Form, message — and this maps them onto the design handoff's tokens so they
 * do not read as a second design system inside the bespoke one. Literal hex
 * values here because antd's theme algorithm derives shades numerically and
 * cannot take a CSS custom property.
 */
const ANTD_THEME = {
  token: {
    colorPrimary: "#0f4f3c",
    colorError: "#8c1d18",
    colorWarning: "#c98a15",
    colorSuccess: "#1c7a5b",
    colorText: "#1a1915",
    colorTextSecondary: "#4e4a42",
    colorTextTertiary: "#7a7568",
    colorBorder: "#e3ded2",
    colorBgContainer: "#ffffff",
    colorBgLayout: "#f7f4ee",
    borderRadius: 6,
    borderRadiusLG: 12,
    fontFamily: "var(--font-body)",
    fontSize: 15,
    // The brief's floor for a low-end Android, applied to antd's controls too.
    controlHeight: 40,
    controlHeightLG: 48,
  },
  components: {
    Modal: { borderRadiusLG: 14 },
    Button: { borderRadius: 8, fontWeight: 600, controlHeight: 36, controlHeightSM: 32, controlHeightLG: 40 },
  },
};

export default function App() {
  return (
    <ConfigProvider theme={ANTD_THEME}>
      {/* AntApp supplies the context that App.useApp()'s message API needs. */}
      <AntApp>
        <BrowserRouter>
          <AuthProvider>
            <LanguageProvider>
            <Routes>
              {/* The bare login card this replaces lived here. Kept as a
                  redirect rather than deleted outright: it is the URL the
                  401 handler used to send people to, so it is in browser
                  histories and in at least one runbook. */}
              <Route path="/login" element={<Navigate to="/" replace />} />
              {/* `/` is public. Signed out it is the landing page; signed in it
                  is the redirect it has always been, so the sign-in form does
                  not need to restate where each role goes. Outside AppLayout
                  because the landing page carries its own chrome and must
                  render for somebody with no account at all. */}
              <Route path="/" element={<Root />} />
              <Route element={<AppLayout />}>
                {/* The four tiers. Each is a first-class sidebar destination;
                    the index picks the one this role is actually for, rather
                    than showing everyone tier 1. */}
                <Route path="/dashboard" element={<DashboardLayout />}>
                  <Route index element={<DashboardHome />} />
                  <Route path="my-work" element={<Tier path="my-work"><MyWorkPage /></Tier>} />
                  <Route path="woreda" element={<Tier path="woreda"><WoredaPage /></Tier>} />
                  <Route path="programme" element={<Tier path="programme"><ProgrammePage /></Tier>} />
                  <Route path="results" element={<Tier path="results"><ResultsPage /></Tier>} />
                </Route>
                <Route path="/cases" element={<CaseListPage />} />
                <Route path="/cases/:caseId" element={<CaseDetailPage />} />
                <Route path="/referrals" element={<ReferralsPage />} />
                <Route path="/alerts" element={<AlertsPage />} />
                <Route path="/youth" element={<YouthListPage />} />
                {/* `/delivery` is the rail's single entry; the four paths are
                    unchanged, so links and bookmarks that predate the tabs
                    still work. */}
                <Route path="/delivery" element={<DeliveryHome />} />
                <Route path="/training" element={<Delivery path="/training"><TrainingPage /></Delivery>} />
                <Route path="/placements" element={<Delivery path="/placements"><PlacementsPage /></Delivery>} />
                <Route path="/enterprises" element={<Delivery path="/enterprises"><EnterprisesPage /></Delivery>} />
                <Route path="/verification" element={<Delivery path="/verification"><VerificationPage /></Delivery>} />
                <Route path="/grievances" element={<GrievancesPage />} />
                <Route path="/grievances/:grievanceId" element={<GrievanceCasePage />} />
                <Route path="/partners" element={<PartnersPage />} />
                {/* WLT group module. Its own prefix: a separate programme with
                    a separate subject, and roles that see no case content. */}
                <Route path="/wlt/beneficiaries" element={<BeneficiariesPage />} />
                <Route path="/wlt/beneficiaries/:profileId" element={<JourneyPage />} />
                {/* One rail entry, four tiers as tabs — the same shape the youth
                    dashboard now uses. `/wlt/dashboard` lands each role on its
                    own: a facilitator on her queue, a region officer on the
                    programme view. */}
                <Route path="/wlt/dashboard" element={<WltDashboardHome />} />
                <Route path="/wlt/dashboard/home" element={<WltTier path="home"><FacilitatorHomePage /></WltTier>} />
                {/* Guarded, like the tier route above it. Without this a
                    woreda officer reached the programme tier by typing the URL
                    — the tab strip did not offer it and nothing refused it. */}
                <Route path="/wlt/dashboard/:tier" element={<WltTierRoute />} />
                <Route path="/wlt/home" element={<Navigate to="/wlt/dashboard/home" replace />} />
                <Route path="/wlt/groups" element={<GroupsPage />} />
                <Route path="/wlt/groups/:groupId" element={<GroupReadinessPage />} />
                {/* Tabs are routes: a link to the roster is a link to the
                    roster, refreshing keeps you where you were, and back steps
                    between sections rather than leaving the group. */}
                <Route path="/wlt/groups/:groupId/:tab" element={<GroupReadinessPage />} />
                {/* The weekly meeting: attendance, savings, and the cash count.
                    Its own route rather than a panel — it is worked through in a
                    room, in order, and it is the screen the offline client will
                    need first. */}
                <Route path="/wlt/groups/:groupId/meetings/:meetingId" element={<MeetingPage />} />
                <Route path="/wlt/linkages" element={<LinkagesPage />} />
                <Route path="/wlt/linkages/:linkageId" element={<LinkageDetailPage />} />
                <Route path="/wlt/cla-readiness" element={<ClaReadinessPage />} />
                <Route path="/wlt/federation-readiness" element={<FederationReadinessPage />} />
                <Route path="/users" element={<UsersPage />} />
              </Route>
              {/* Unknown paths go through Home so the landing screen stays role-aware. */}
              {/* D16: an unknown URL said nothing and silently landed on the
                  home route, so a URL-tampering permission test could not tell
                  "you may not see this" from "that page does not exist". */}
              <Route path="*" element={<NotFoundPage />} />
              </Routes>
            </LanguageProvider>
          </AuthProvider>
        </BrowserRouter>
      </AntApp>
    </ConfigProvider>
  );
}
