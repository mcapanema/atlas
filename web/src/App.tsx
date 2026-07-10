import { Navigate, Route, Routes } from "react-router-dom";

import { AppLayout } from "./components/AppLayout";
import { ConnectorsPage } from "./pages/ConnectorsPage";
import { MetricsPage } from "./pages/MetricsPage";
import { OrganizationsPage } from "./pages/OrganizationsPage";
import { WorkItemPage } from "./pages/WorkItemPage";
import { WorkItemsPage } from "./pages/WorkItemsPage";

export function App() {
  return (
    <AppLayout>
      <Routes>
        <Route path="/" element={<Navigate to="/organizations" replace />} />
        <Route path="/organizations" element={<OrganizationsPage />} />
        <Route path="/work-items" element={<WorkItemsPage />} />
        <Route path="/work-items/:id" element={<WorkItemPage />} />
        <Route path="/metrics" element={<MetricsPage />} />
        <Route path="/connectors" element={<ConnectorsPage />} />
      </Routes>
    </AppLayout>
  );
}
