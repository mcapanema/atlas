import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, requestUrl } from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { OrganizationsPage } from "./OrganizationsPage";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("OrganizationsPage", () => {
  it("renders organizations returned by the API", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) =>
      Promise.resolve(
        jsonResponse(
          requestUrl(input).startsWith("/api/people")
            ? []
            : [
                {
                  id: "11111111-1111-1111-1111-111111111111",
                  name: "Acme",
                  created_at: "2026-07-08T00:00:00Z",
                },
              ],
        ),
      ),
    );

    renderWithClient(<OrganizationsPage />);

    await waitFor(() => expect(screen.getByText("Acme")).toBeInTheDocument());
  });

  it("shows an error when organizations fail to load", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({}, 500));

    renderWithClient(<OrganizationsPage />);

    await waitFor(() =>
      expect(screen.getByText("Failed to load organizations")).toBeInTheDocument(),
    );
  });

  describe("people", () => {
    const person = {
      id: "22222222-2222-2222-2222-222222222222",
      organization_id: "11111111-1111-1111-1111-111111111111",
      name: "Joao B",
      display_name: null,
      shown_name: "Joao B",
      email: "joao@acme.test",
    };

    function mockApi(people: unknown[]) {
      return vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
        const url = requestUrl(input);
        if (url.startsWith("/api/people/")) return Promise.resolve(jsonResponse(person));
        return Promise.resolve(jsonResponse(url.startsWith("/api/people") ? people : []));
      });
    }

    async function editDisplayName(text: string) {
      fireEvent.click(await screen.findByRole("button", { name: /edit/i }));
      const input = screen.getByRole("textbox");
      fireEvent.change(input, { target: { value: text } });
      fireEvent.keyDown(input, { key: "Enter", keyCode: 13 });
      fireEvent.keyUp(input, { key: "Enter", keyCode: 13 });
    }

    function patchCall(spy: ReturnType<typeof mockApi>) {
      return spy.mock.calls.find(([, init]) => init?.method === "PATCH");
    }

    it("renders people with their Linear name and display name", async () => {
      mockApi([person, { ...person, id: "3", name: "Ana", email: null, display_name: "Ana L" }]);

      renderWithClient(<OrganizationsPage />);

      expect(await screen.findByText("Joao B")).toBeInTheDocument();
      expect(screen.getByText("People")).toBeInTheDocument();
      expect(screen.getByText("joao@acme.test")).toBeInTheDocument();
      expect(screen.getByText("Ana L")).toBeInTheDocument();
      expect(screen.getAllByText("—")).toHaveLength(2);
    });

    it("saves a display name", async () => {
      const spy = mockApi([person]);
      renderWithClient(<OrganizationsPage />);

      await editDisplayName("João Barbosa");

      await waitFor(() => expect(patchCall(spy)).toBeDefined());
      const [url, init] = patchCall(spy)!;
      expect(requestUrl(url)).toBe(`/api/people/${person.id}`);
      expect(init?.body).toBe(JSON.stringify({ display_name: "João Barbosa" }));
    });

    it("clears a display name", async () => {
      const spy = mockApi([{ ...person, display_name: "Old" }]);
      renderWithClient(<OrganizationsPage />);

      await editDisplayName("");

      await waitFor(() => expect(patchCall(spy)).toBeDefined());
      expect(patchCall(spy)![1]?.body).toBe(JSON.stringify({ display_name: null }));
    });

    it("shows an error when saving fails", async () => {
      vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
        if (init?.method === "PATCH") {
          return Promise.resolve(jsonResponse({ detail: "too long" }, 422));
        }
        return Promise.resolve(
          jsonResponse(requestUrl(input).startsWith("/api/people") ? [person] : []),
        );
      });
      renderWithClient(<OrganizationsPage />);

      await editDisplayName("x");

      expect(await screen.findByText("Couldn't save the display name")).toBeInTheDocument();
      expect(screen.getByText("too long")).toBeInTheDocument();
    });

    it("explains the empty state", async () => {
      mockApi([]);
      renderWithClient(<OrganizationsPage />);

      expect(await screen.findByText("People appear after the first sync.")).toBeInTheDocument();
    });
  });
});
