import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";

/**
 * Render under a fresh QueryClient (retries off) + MemoryRouter.
 * Implemented via RTL's `wrapper` option so `rerender` re-applies the
 * same providers (FlowDashboard's option-identity test relies on that).
 * The router is harmless for components that don't route; pages that
 * need a location pass `initialEntries`.
 */
export function renderWithClient(
  ui: ReactElement,
  initialEntries: string[] = ["/"],
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(ui, {
    wrapper: ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={initialEntries}>{children}</MemoryRouter>
      </QueryClientProvider>
    ),
  });
}
