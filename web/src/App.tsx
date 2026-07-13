import { Spin } from "antd";
import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { AppLayout } from "./components/AppLayout";
import { AdvisorPage } from "./pages/AdvisorPage";
import { ConnectorsPage } from "./pages/ConnectorsPage";
import { ExecutiveDashboardPage } from "./pages/ExecutiveDashboardPage";
import { MeetingsPage } from "./pages/MeetingsPage";
import { OrganizationsPage } from "./pages/OrganizationsPage";
import { WorkItemPage } from "./pages/WorkItemPage";
import { WorkItemsPage } from "./pages/WorkItemsPage";

// Only these two routes reach ECharts (via FlowDashboard); lazy-loading them
// keeps the chart bundle out of the initial chunk. Other pages share the main
// chunk's dependencies — lazy-loading them would add flicker for no size win.
const TeamDashboardPage = lazy(() =>
  import("./pages/TeamDashboardPage").then((m) => ({ default: m.TeamDashboardPage })),
);
const ProjectDashboardPage = lazy(() =>
  import("./pages/ProjectDashboardPage").then((m) => ({ default: m.ProjectDashboardPage })),
);

export function App() {
  return (
    <AppLayout>
      <Suspense fallback={<Spin style={{ display: "block", marginTop: 48 }} />}>
        <Routes>
          <Route path="/" element={<ExecutiveDashboardPage />} />
          <Route path="/organizations" element={<OrganizationsPage />} />
          <Route path="/work-items" element={<WorkItemsPage />} />
          <Route path="/work-items/:id" element={<WorkItemPage />} />
          <Route path="/teams" element={<TeamDashboardPage />} />
          <Route path="/projects" element={<ProjectDashboardPage />} />
          <Route path="/advisor" element={<AdvisorPage />} />
          <Route path="/meetings" element={<MeetingsPage />} />
          <Route path="/metrics" element={<Navigate to="/teams" replace />} />
          <Route path="/connectors" element={<ConnectorsPage />} />
        </Routes>
      </Suspense>
    </AppLayout>
  );
}
