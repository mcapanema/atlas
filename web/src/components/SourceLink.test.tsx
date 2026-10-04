import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SourceLink } from "./SourceLink";

describe("SourceLink", () => {
  it("links to the origin in a new tab, labelled with the host", () => {
    render(<SourceLink url="https://linear.app/acme/issue/ENG-1/fix-login" />);

    const link = screen.getByRole("link", { name: /linear\.app/ });
    expect(link).toHaveAttribute("href", "https://linear.app/acme/issue/ENG-1/fix-login");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("renders a dash when there is no url", () => {
    render(<SourceLink url={null} />);

    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it.each(["javascript:alert(1)", "not a url", "ftp://example.com/x"])("never links %s", (url) => {
    render(<SourceLink url={url} />);

    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});
