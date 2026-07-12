import "@fontsource-variable/red-hat-display";
import "@fontsource-variable/red-hat-text";
import "@fontsource-variable/red-hat-mono";
import "./index.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { App } from "./App";
import { ThemeProvider } from "./theme/ThemeProvider";

// Dashboards refetch on every window focus with the default staleTime of 0;
// 30s keeps tab-switching cheap while staying fresh enough for delivery data.
const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000 } },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </ThemeProvider>
    </QueryClientProvider>
  </StrictMode>,
);
