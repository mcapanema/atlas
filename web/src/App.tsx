import { Navigate, Route, Routes } from "react-router-dom";

import { AppLayout } from "./components/AppLayout";
import { OrganizationsPage } from "./pages/OrganizationsPage";

export function App() {
  return (
    <AppLayout>
      <Routes>
        <Route path="/" element={<Navigate to="/organizations" replace />} />
        <Route path="/organizations" element={<OrganizationsPage />} />
      </Routes>
    </AppLayout>
  );
}
