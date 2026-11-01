import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, requestUrl } from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { ChangePasswordModal } from "./ChangePasswordModal";

afterEach(() => {
  vi.restoreAllMocks();
});

function fill(current: string, next: string, confirm: string) {
  fireEvent.change(screen.getByLabelText("Current password"), { target: { value: current } });
  fireEvent.change(screen.getByLabelText("New password"), { target: { value: next } });
  fireEvent.change(screen.getByLabelText("Confirm new password"), { target: { value: confirm } });
  fireEvent.click(screen.getByRole("button", { name: "Change password" }));
}

describe("ChangePasswordModal", () => {
  it("rejects a mismatch without sending anything", async () => {
    const spy = vi.spyOn(globalThis, "fetch");
    renderWithClient(<ChangePasswordModal open onClose={vi.fn()} />);
    fill("old-password-1", "new-password-12", "new-password-13");
    expect(await screen.findByText("The passwords don't match")).toBeInTheDocument();
    expect(spy).not.toHaveBeenCalled();
  });

  it("requires the minimum length", async () => {
    const spy = vi.spyOn(globalThis, "fetch");
    renderWithClient(<ChangePasswordModal open onClose={vi.fn()} />);
    fill("old-password-1", "short", "short");
    expect(await screen.findAllByText("At least 12 characters")).not.toHaveLength(0);
    expect(spy).not.toHaveBeenCalled();
  });

  it("changes the password, closes and confirms", async () => {
    const spy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(null, { status: 204 }));
    const onClose = vi.fn();
    renderWithClient(<ChangePasswordModal open onClose={onClose} />);
    fill("old-password-1", "new-password-12", "new-password-12");
    await waitFor(() => {
      expect(onClose).toHaveBeenCalled();
    });
    expect(requestUrl(spy.mock.calls[0][0])).toBe("/api/auth/password");
    expect(spy.mock.calls[0][1]?.method).toBe("PUT");
    expect(spy.mock.calls[0][1]?.body).toBe(
      JSON.stringify({ current_password: "old-password-1", new_password: "new-password-12" }),
    );
    expect(await screen.findByText("Password changed")).toBeInTheDocument();
  });

  it("shows the server's reason inside the dialog", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ detail: "Current password is incorrect" }, 422),
    );
    const onClose = vi.fn();
    renderWithClient(<ChangePasswordModal open onClose={onClose} />);
    fill("wrong-password-1", "new-password-12", "new-password-12");
    const text = await screen.findByText("Current password is incorrect");
    expect(text.closest(".ant-alert-error")).not.toBeNull();
    expect(onClose).not.toHaveBeenCalled();
  });
});
