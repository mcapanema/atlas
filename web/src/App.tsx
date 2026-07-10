import { Navigate, Route, Routes } from "react-router-dom";

import { AppLayout } from "./components/AppLayout";
import { ConnectorsPage } from "./pages/ConnectorsPage";
import { OrganizationsPage } from "./pages/OrganizationsPage";
import { ProjectDashboardPage } from "./pages/ProjectDashboardPage";
import { TeamDashboardPage } from "./pages/TeamDashboardPage";
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
        <Route path="/teams" element={<TeamDashboardPage />} />
        <Route path="/projects" element={<ProjectDashboardPage />} />
        <Route path="/metrics" element={<Navigate to="/teams" replace />} />
        <Route path="/connectors" element={<ConnectorsPage />} />
      </Routes>
    </AppLayout>
  );
}
