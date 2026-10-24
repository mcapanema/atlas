import { describe, expect, it } from "vitest";

import { teamFixture } from "../test/fixtures";
import {
  recomputeOrganization,
  scopeFromParams,
  scopeParams,
  workspaceOrganization,
} from "./rulesScope";

describe("scope helpers", () => {
  it("finds the organization of a workspace scope only", () => {
    const org = { id: "o1", name: "Acme", created_at: "2026-07-01T00:00:00Z" };
    expect(workspaceOrganization({ kind: "organization", id: "o1" }, [org])).toBe(org);
    expect(workspaceOrganization({ kind: "organization", id: "o2" }, [org])).toBeUndefined();
    expect(workspaceOrganization({ kind: "team", id: "o1" }, [org])).toBeUndefined();
    expect(workspaceOrganization(undefined, [org])).toBeUndefined();
  });

  it("prefers a team, then the org param, then the first organization", () => {
    expect(scopeFromParams(new URLSearchParams("team=t1&org=o1"), "o0")).toEqual({
      kind: "team",
      id: "t1",
    });
    expect(scopeFromParams(new URLSearchParams("org=o1"), "o0")).toEqual({
      kind: "organization",
      id: "o1",
    });
    expect(scopeFromParams(new URLSearchParams(), "o0")).toEqual({
      kind: "organization",
      id: "o0",
    });
    expect(scopeFromParams(new URLSearchParams(), undefined)).toBeUndefined();
  });

  it("maps a picker value to search params", () => {
    expect(scopeParams("team:t1")).toEqual({ team: "t1" });
    expect(scopeParams("organization:o1")).toEqual({ org: "o1" });
  });

  it("finds the organization whose history a scope's recompute rewrites", () => {
    const team = { ...teamFixture, has_custom_rules: false };
    expect(recomputeOrganization({ kind: "team", id: team.id }, [team])).toBe(team.organization_id);
    expect(recomputeOrganization({ kind: "organization", id: "o1" }, undefined)).toBe("o1");
  });
});
