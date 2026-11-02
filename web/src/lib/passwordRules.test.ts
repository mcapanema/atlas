import { describe, expect, it } from "vitest";

import {
  MAX_PASSWORD_LENGTH,
  MIN_PASSWORD_LENGTH,
  PASSWORD_HINT,
  confirmProps,
  newPasswordRules,
} from "./passwordRules";

describe("passwordRules", () => {
  it("states the minimum in the hint", () => {
    expect(MIN_PASSWORD_LENGTH).toBe(12);
    expect(PASSWORD_HINT).toBe("At least 12 characters");
  });

  it("requires, bounds the length and uses the given required message", () => {
    expect(newPasswordRules("Enter a password")).toEqual([
      { required: true, message: "Enter a password" },
      { min: 12, message: "At least 12 characters" },
      { max: MAX_PASSWORD_LENGTH, message: "At most 128 characters" },
    ]);
  });

  it("confirm depends on its field and rejects a mismatch", async () => {
    const props = confirmProps("new_password", "Confirm it");
    expect(props.dependencies).toEqual(["new_password"]);
    expect(props.rules[0]).toEqual({ required: true, message: "Confirm it" });
    const make = props.rules[1] as unknown as (form: {
      getFieldValue: (name: string) => unknown;
    }) => { validator: (rule: unknown, value?: string) => Promise<void> };
    const { validator } = make({ getFieldValue: () => "secret-password-1" });
    await expect(validator({}, "secret-password-1")).resolves.toBeUndefined();
    await expect(validator({}, undefined)).resolves.toBeUndefined();
    await expect(validator({}, "other")).rejects.toThrow("The passwords don't match");
  });
});
