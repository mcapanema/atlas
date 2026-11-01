import type { Rule } from "antd/es/form";

/** Mirrors the backend's password length bounds (the max bounds scrypt work per request). */
export const MIN_PASSWORD_LENGTH = 12;
export const MAX_PASSWORD_LENGTH = 128;

export const PASSWORD_HINT = `At least ${MIN_PASSWORD_LENGTH} characters`;

/** The length bounds alone: sign-in only enforces them while creating the first account. */
export const passwordLengthRules: Rule[] = [
  { min: MIN_PASSWORD_LENGTH, message: PASSWORD_HINT },
  { max: MAX_PASSWORD_LENGTH, message: `At most ${MAX_PASSWORD_LENGTH} characters` },
];

/** Form rules for a password being chosen (not one being typed to sign in). */
export function newPasswordRules(requiredMessage: string): Rule[] {
  return [{ required: true, message: requiredMessage }, ...passwordLengthRules];
}

/** Props for a "confirm" Form.Item that must equal the `field` item's value. */
export function confirmProps(field: string, requiredMessage: string) {
  return {
    dependencies: [field],
    rules: [
      { required: true, message: requiredMessage },
      ({ getFieldValue }: { getFieldValue: (name: string) => unknown }) => ({
        validator: (_: unknown, value: string | undefined) =>
          !value || getFieldValue(field) === value
            ? Promise.resolve()
            : Promise.reject(new Error("The passwords don't match")),
      }),
    ] as Rule[],
  };
}
