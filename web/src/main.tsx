import "@fontsource-variable/red-hat-display";
import "@fontsource-variable/red-hat-text";
import "@fontsource-variable/red-hat-mono";
import "./index.css";

import { QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { createQueryClient } from "./api/queryClient";
import { App } from "./App";
import { ThemeProvider } from "./theme/ThemeProvider";

const queryClient = createQueryClient();

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
