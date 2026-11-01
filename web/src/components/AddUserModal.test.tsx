import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, requestUrl } from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { AddUserModal } from "./AddUserModal";

afterEach(() => {
  vi.restoreAllMocks();
});

function fill(name: string, email: string, password: string) {
  fireEvent.change(screen.getByLabelText("Name"), { target: { value: name } });
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: email } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: password } });
}

describe("AddUserModal", () => {
  it("creates a member with a trimmed email and closes", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({}, 201));
    const onClose = vi.fn();
    renderWithClient(<AddUserModal open onClose={onClose} />);
    expect(screen.getByText("At least 12 characters")).toBeInTheDocument();
    fill("Ana", " ana@acme.com ", "long-enough-pw-1");
    fireEvent.click(screen.getByRole("button", { name: "Add user" }));
    await waitFor(() => {
      expect(onClose).toHaveBeenCalled();
    });
    expect(requestUrl(spy.mock.calls[0][0])).toBe("/api/users");
    expect(spy.mock.calls[0][1]?.method).toBe("POST");
    expect(spy.mock.calls[0][1]?.body).toBe(
      JSON.stringify({
        email: "ana@acme.com",
        name: "Ana",
        password: "long-enough-pw-1",
        is_admin: false,
      }),
    );
  });

  it("can make the account an administrator", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({}, 201));
    renderWithClient(<AddUserModal open onClose={vi.fn()} />);
    fill("Bo", "bo@acme.com", "long-enough-pw-1");
    fireEvent.click(screen.getByLabelText("Administrator"));
    fireEvent.click(screen.getByRole("button", { name: "Add user" }));
    await waitFor(() => {
      expect(spy).toHaveBeenCalled();
    });
    expect(JSON.parse(spy.mock.calls[0][1]?.body as string)).toMatchObject({ is_admin: true });
  });

  it("requires the minimum password length", async () => {
    const spy = vi.spyOn(globalThis, "fetch");
    renderWithClient(<AddUserModal open onClose={vi.fn()} />);
    fill("Ana", "ana@acme.com", "short");
    fireEvent.click(screen.getByRole("button", { name: "Add user" }));
    await waitFor(() => {
      expect(screen.getAllByText("At least 12 characters").length).toBeGreaterThan(1);
    });
    expect(spy).not.toHaveBeenCalled();
  });

  it("shows a taken email inside the dialog", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ detail: "That email already has an account" }, 409),
    );
    const onClose = vi.fn();
    renderWithClient(<AddUserModal open onClose={onClose} />);
    fill("Ana", "ana@acme.com", "long-enough-pw-1");
    fireEvent.click(screen.getByRole("button", { name: "Add user" }));
    const text = await screen.findByText("That email already has an account");
    expect(text.closest(".ant-alert-error")).not.toBeNull();
    expect(onClose).not.toHaveBeenCalled();
  });

  it("sends one request when submitted twice", async () => {
    const spy = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(() => new Promise<Response>(() => undefined));
    renderWithClient(<AddUserModal open onClose={vi.fn()} />);
    fill("Ana", "ana@acme.com", "long-enough-pw-1");
    const button = screen.getByRole("button", { name: "Add user" });
    fireEvent.click(button);
    fireEvent.click(button);
    await waitFor(() => {
      expect(spy).toHaveBeenCalledTimes(1);
    });
  });
});
