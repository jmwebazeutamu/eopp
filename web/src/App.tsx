import { App as AntApp, ConfigProvider } from "antd";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import AppLayout from "./components/AppLayout";
import { AuthProvider } from "./auth/AuthContext";
import AlertsPage from "./pages/AlertsPage";
import CaseDetailPage from "./pages/CaseDetailPage";
import CaseListPage from "./pages/CaseListPage";
import LoginPage from "./pages/LoginPage";
import PartnersPage from "./pages/PartnersPage";
import UsersPage from "./pages/UsersPage";
import YouthListPage from "./pages/YouthListPage";

export default function App() {
  return (
    <ConfigProvider theme={{ token: { colorPrimary: "#1668dc", borderRadius: 6 } }}>
      {/* AntApp supplies the context that App.useApp()'s message API needs. */}
      <AntApp>
        <BrowserRouter>
          <AuthProvider>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route element={<AppLayout />}>
                <Route path="/cases" element={<CaseListPage />} />
                <Route path="/cases/:caseId" element={<CaseDetailPage />} />
                <Route path="/alerts" element={<AlertsPage />} />
                <Route path="/youth" element={<YouthListPage />} />
                <Route path="/partners" element={<PartnersPage />} />
                <Route path="/users" element={<UsersPage />} />
              </Route>
              <Route path="*" element={<Navigate to="/cases" replace />} />
            </Routes>
          </AuthProvider>
        </BrowserRouter>
      </AntApp>
    </ConfigProvider>
  );
}
