import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, requestUrl } from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { SignInPage } from "./SignInPage";

afterEach(() => {
  vi.restoreAllMocks();
});

function type(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

function submit(name: string) {
  fireEvent.click(screen.getByRole("button", { name }));
}

describe("SignInPage — sign in", () => {
  it("titles the page and offers the browser's saved credentials", () => {
    renderWithClient(<SignInPage setupRequired={false} />);
    expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(document.title).toBe("Atlas — Sign in");
    expect(screen.getByLabelText("Email")).toHaveAttribute("autocomplete", "username");
    expect(screen.getByLabelText("Password")).toHaveAttribute("autocomplete", "current-password");
    expect(screen.queryByLabelText("Name")).not.toBeInTheDocument();
  });

  it("posts the credentials and shows the server's reason on failure", async () => {
    const spy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(jsonResponse({ detail: "Wrong email or password" }, 401));
    renderWithClient(<SignInPage setupRequired={false} />);

    type("Email", "ana@acme.com");
    type("Password", "not-the-password");
    submit("Sign in");

    const alert = await screen.findByText("Wrong email or password");
    expect(alert.closest(".ant-alert-error")).not.toBeNull();
    expect(requestUrl(spy.mock.calls[0][0])).toBe("/api/auth/sign-in");
    expect(spy.mock.calls[0][1]?.method).toBe("POST");
    expect(spy.mock.calls[0][1]?.body).toBe(
      JSON.stringify({ email: "ana@acme.com", password: "not-the-password" }),
    );
  });
});

describe("SignInPage — email field", () => {
  it("trims spaces around the email and sends the request", async () => {
    const spy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(jsonResponse({ detail: "Wrong email or password" }, 401));
    renderWithClient(<SignInPage setupRequired={false} />);

    type("Email", " Ana@Acme.com ");
    type("Password", "not-the-password");
    submit("Sign in");

    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(spy.mock.calls[0][1]?.body).toBe(
      JSON.stringify({ email: "Ana@Acme.com", password: "not-the-password" }),
    );
  });

  it("says a malformed email is not valid, without a request", async () => {
    const spy = vi.spyOn(globalThis, "fetch");
    renderWithClient(<SignInPage setupRequired={false} />);

    type("Email", "ana-at-acme");
    type("Password", "not-the-password");
    submit("Sign in");

    expect(await screen.findByText("Enter a valid email address")).toBeInTheDocument();
    expect(screen.queryByText("Enter your email address")).not.toBeInTheDocument();
    expect(spy).not.toHaveBeenCalled();
  });
});

describe("SignInPage — first run", () => {
  it("explains that the first account is the administrator", () => {
    renderWithClient(<SignInPage setupRequired />);
    expect(screen.getByRole("heading", { name: "Create the first account" })).toBeInTheDocument();
    expect(document.title).toBe("Atlas — Create the first account");
    expect(
      screen.getByText(
        "This account becomes the administrator. Add the rest of the team from Setup → Users.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toHaveAttribute("autocomplete", "username");
    expect(screen.getByLabelText("Password")).toHaveAttribute("autocomplete", "new-password");
  });

  it("posts the new account to setup", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse(
        {
          id: "u1",
          email: "ana@acme.com",
          name: "Ana",
          is_admin: true,
          created_at: "2026-10-31T00:00:00Z",
        },
        201,
      ),
    );
    renderWithClient(<SignInPage setupRequired />);

    type("Email", "ana@acme.com");
    type("Name", "Ana");
    type("Password", "correct-horse-battery");
    submit("Create account");

    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(requestUrl(spy.mock.calls[0][0])).toBe("/api/auth/setup");
    expect(spy.mock.calls[0][1]?.body).toBe(
      JSON.stringify({ email: "ana@acme.com", name: "Ana", password: "correct-horse-battery" }),
    );
  });

  it("rejects a password shorter than 12 characters without a request", async () => {
    const spy = vi.spyOn(globalThis, "fetch");
    renderWithClient(<SignInPage setupRequired />);

    type("Email", "ana@acme.com");
    type("Name", "Ana");
    type("Password", "elevenchars");
    submit("Create account");

    await waitFor(() =>
      expect(document.querySelector(".ant-form-item-explain-error")).toHaveTextContent(
        "At least 12 characters",
      ),
    );
    expect(spy).not.toHaveBeenCalled();
  });
});
