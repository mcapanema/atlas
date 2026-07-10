import { Navigate, Route, Routes } from "react-router-dom";

import { AppLayout } from "./components/AppLayout";
import { ConnectorsPage } from "./pages/ConnectorsPage";
import { OrganizationsPage } from "./pages/OrganizationsPage";
import { WorkItemsPage } from "./pages/WorkItemsPage";

export function App() {
  return (
    <AppLayout>
      <Routes>
        <Route path="/" element={<Navigate to="/organizations" replace />} />
        <Route path="/organizations" element={<OrganizationsPage />} />
        <Route path="/work-items" element={<WorkItemsPage />} />
        <Route path="/connectors" element={<ConnectorsPage />} />
      </Routes>
    </AppLayout>
  );
}
