import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, requestUrl } from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { ResetPasswordModal } from "./ResetPasswordModal";

afterEach(() => {
  vi.restoreAllMocks();
});

const ana = {
  id: "66666666-6666-6666-6666-666666666666",
  email: "ana@acme.com",
  name: "Ana",
  is_admin: false,
  created_at: "2026-10-31T10:30:00Z",
};

function fill(next: string, confirm: string) {
  fireEvent.change(screen.getByLabelText("New password"), { target: { value: next } });
  fireEvent.change(screen.getByLabelText("Confirm new password"), { target: { value: confirm } });
  fireEvent.click(screen.getByRole("button", { name: "Reset password" }));
}

describe("ResetPasswordModal", () => {
  it("names the user in the title", () => {
    renderWithClient(<ResetPasswordModal user={ana} onClose={vi.fn()} />);
    expect(screen.getByText("Reset password for Ana")).toBeInTheDocument();
  });

  it("renders nothing without a user", () => {
    renderWithClient(<ResetPasswordModal user={null} onClose={vi.fn()} />);
    expect(screen.queryByText(/Reset password for/)).toBeNull();
  });

  it("rejects a mismatch without sending anything", async () => {
    const spy = vi.spyOn(globalThis, "fetch");
    renderWithClient(<ResetPasswordModal user={ana} onClose={vi.fn()} />);
    fill("new-password-12", "new-password-13");
    expect(await screen.findByText("The passwords don't match")).toBeInTheDocument();
    expect(spy).not.toHaveBeenCalled();
  });

  it("resets the password, closes and confirms", async () => {
    const spy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(null, { status: 204 }));
    const onClose = vi.fn();
    renderWithClient(<ResetPasswordModal user={ana} onClose={onClose} />);
    fill("new-password-12", "new-password-12");
    await waitFor(() => {
      expect(onClose).toHaveBeenCalled();
    });
    expect(requestUrl(spy.mock.calls[0][0])).toBe(`/api/users/${ana.id}/password`);
    expect(spy.mock.calls[0][1]?.method).toBe("PUT");
    expect(spy.mock.calls[0][1]?.body).toBe(JSON.stringify({ new_password: "new-password-12" }));
    expect(await screen.findByText("Password reset. Ana's sessions ended.")).toBeInTheDocument();
  });

  it("shows the server's reason inside the dialog", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ detail: "No such user" }, 404));
    const onClose = vi.fn();
    renderWithClient(<ResetPasswordModal user={ana} onClose={onClose} />);
    fill("new-password-12", "new-password-12");
    const text = await screen.findByText("No such user");
    expect(text.closest(".ant-alert-error")).not.toBeNull();
    expect(onClose).not.toHaveBeenCalled();
  });
});
