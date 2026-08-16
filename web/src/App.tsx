import { App as AntApp, ConfigProvider } from "antd";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import AppLayout from "./components/AppLayout";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import { LanguageProvider } from "./i18n/LanguageContext";
import AlertsPage from "./pages/AlertsPage";
import CaseDetailPage from "./pages/CaseDetailPage";
import CaseListPage from "./pages/CaseListPage";
import LoginPage from "./pages/LoginPage";
import PartnersPage from "./pages/PartnersPage";
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
  return <Navigate to="/cases" replace />;
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
    Button: { borderRadius: 8, fontWeight: 600 },
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
                <Route path="/cases" element={<CaseListPage />} />
                <Route path="/cases/:caseId" element={<CaseDetailPage />} />
                <Route path="/referrals" element={<ReferralsPage />} />
                <Route path="/alerts" element={<AlertsPage />} />
                <Route path="/youth" element={<YouthListPage />} />
                <Route path="/partners" element={<PartnersPage />} />
                <Route path="/users" element={<UsersPage />} />
              </Route>
              {/* Unknown paths go through Home so the landing screen stays role-aware. */}
              <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </LanguageProvider>
          </AuthProvider>
        </BrowserRouter>
      </AntApp>
    </ConfigProvider>
  );
}
