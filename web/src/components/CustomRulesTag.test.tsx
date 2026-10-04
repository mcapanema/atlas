import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { teamFixture } from "../test/fixtures";
import { renderWithClient } from "../test/render";
import { CustomRulesTag } from "./CustomRulesTag";

describe("CustomRulesTag", () => {
  it("links a team with custom rules to its rules", () => {
    renderWithClient(<CustomRulesTag team={{ ...teamFixture, has_custom_rules: true }} />);

    expect(screen.getByRole("link", { name: "Custom rules" })).toHaveAttribute(
      "href",
      `/metric-rules?team=${teamFixture.id}`,
    );
  });

  it("renders nothing for a team on the workspace rules", () => {
    const { container } = renderWithClient(<CustomRulesTag team={teamFixture} />);

    expect(container).toBeEmptyDOMElement();
  });
});
