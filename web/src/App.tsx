import { Alert, Spin } from "antd";
import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { useAuthStatus } from "./api/auth";
import { AppLayout } from "./components/AppLayout";
import { AdvisorPage } from "./pages/AdvisorPage";
import { ConnectorsPage } from "./pages/ConnectorsPage";
import { ExecutiveDashboardPage } from "./pages/ExecutiveDashboardPage";
import { MeetingsPage } from "./pages/MeetingsPage";
import { MetricRulesPage } from "./pages/MetricRulesPage";
import { OrganizationsPage } from "./pages/OrganizationsPage";
import { SignInPage } from "./pages/SignInPage";
import { UsersPage } from "./pages/UsersPage";
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

const loading = <Spin style={{ display: "block", marginTop: 48 }} />;

// Signed out, the sign-in screen renders in place of the app at the same URL,
// so signing in lands on the page that was asked for.
export function App() {
  // Data first: a failed background refetch keeps the last known status.
  const { data, isError } = useAuthStatus();
  if (data === undefined) {
    return isError ? <Alert type="error" showIcon title="Couldn't reach Atlas" /> : loading;
  }
  if (data.user === null) return <SignInPage setupRequired={data.setup_required} />;
  return <SignedInApp />;
}

function SignedInApp() {
  return (
    <AppLayout>
      <Suspense fallback={loading}>
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
          <Route path="/metric-rules" element={<MetricRulesPage />} />
          <Route path="/users" element={<UsersPage />} />
        </Routes>
      </Suspense>
    </AppLayout>
  );
}
