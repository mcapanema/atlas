import { Navigate, Route, Routes } from "react-router-dom";

import { AppLayout } from "./components/AppLayout";

export function App() {
  return (
    <AppLayout>
      <Routes>
        <Route path="/" element={<Navigate to="/organizations" replace />} />
        <Route path="/organizations" element={<div>Organizations</div>} />
      </Routes>
    </AppLayout>
  );
}
