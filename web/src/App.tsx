import { App as AntApp, ConfigProvider } from "antd";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import AppLayout from "./components/AppLayout";
import type { ReactNode } from "react";

import { AuthProvider, useAuth } from "./auth/AuthContext";
import { LanguageProvider } from "./i18n/LanguageContext";
import { canSeeTier, landingTier } from "./pages/dashboard/tierAccess";
import TierUnavailablePage from "./pages/dashboard/TierUnavailablePage";
import AlertsPage from "./pages/AlertsPage";
import CaseDetailPage from "./pages/CaseDetailPage";
import CaseListPage from "./pages/CaseListPage";
import DashboardLayout from "./pages/dashboard/DashboardLayout";
import MyWorkPage from "./pages/dashboard/MyWorkPage";
import ProgrammePage from "./pages/dashboard/ProgrammePage";
import ResultsPage from "./pages/dashboard/ResultsPage";
import WoredaPage from "./pages/dashboard/WoredaPage";
import LoginPage from "./pages/LoginPage";
import EnterprisesPage from "./pages/EnterprisesPage";
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
  // Nothing at all: not the system administrator since the 2026-08-16
  // deviation, but still any role the matrix does not cover.
  if (user.access.case_scope === "NONE") return <Navigate to="/users" replace />;
  // A role that reads case records widely but writes none of them is a
  // supervisory one, and the handoff designs the dashboard for exactly them.
  // Case-facing roles keep landing on their caseload, which is their work.
  //
  if (!user.access.case_write) return <Navigate to="/dashboard" replace />;
  return <Navigate to="/cases" replace />;
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
              <Route path="/login" element={<LoginPage />} />
              <Route element={<AppLayout />}>
                <Route index element={<Home />} />
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
                <Route path="/training" element={<TrainingPage />} />
                <Route path="/placements" element={<PlacementsPage />} />
                <Route path="/enterprises" element={<EnterprisesPage />} />
                <Route path="/verification" element={<VerificationPage />} />
                <Route path="/grievances" element={<GrievancesPage />} />
                <Route path="/partners" element={<PartnersPage />} />
                {/* WLT group module. Its own prefix: a separate programme with
                    a separate subject, and roles that see no case content. */}
                <Route path="/wlt/beneficiaries" element={<BeneficiariesPage />} />
                <Route path="/wlt/beneficiaries/:profileId" element={<JourneyPage />} />
                <Route path="/wlt/groups" element={<GroupsPage />} />
                <Route path="/wlt/groups/:groupId" element={<GroupReadinessPage />} />
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
