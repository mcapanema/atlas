// Canary for the complexity ceilings CI's lint job enforces (eslint.config.js).
// If the ceilings block is deleted or its `files` glob stops matching product
// code, `eslint .` stays green and the gate vanishes silently — this fails
// instead. Severity only: tuning a ceiling is legitimate, removing it isn't.
import { ESLint, type Linter } from "eslint";

const COMPLEXITY_GATES = [
  "complexity",
  "max-depth",
  "max-params",
  "max-nested-callbacks",
  "max-lines-per-function",
  "max-lines",
];
const ERROR = 2;

async function rulesFor(filePath: string): Promise<Partial<Linter.RulesRecord>> {
  // Default cwd is process.cwd(): web/, where every npm script runs vitest.
  const eslint = new ESLint();
  const config = (await eslint.calculateConfigForFile(filePath)) as Linter.Config;
  return config.rules ?? {};
}

function severity(entry: Linter.RuleEntry | undefined): unknown {
  return Array.isArray(entry) ? entry[0] : entry;
}

describe("ESLint complexity gates", () => {
  it.each(COMPLEXITY_GATES)("errors on %s in product code", async (rule) => {
    const rules = await rulesFor("src/App.tsx");

    expect(severity(rules[rule])).toBe(ERROR);
  });

  it("exempts test files", async () => {
    const rules = await rulesFor("src/App.test.tsx");

    // Absent or explicitly "off"/"warn" are all exempt — only an error gates.
    expect(COMPLEXITY_GATES.filter((rule) => severity(rules[rule]) === ERROR)).toEqual([]);
  });
});
