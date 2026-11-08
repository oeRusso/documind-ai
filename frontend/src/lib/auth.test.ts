import { describe, expect, it } from "vitest";

import { safeNextPath } from "./auth";

describe("safeNextPath", () => {
  it("keeps internal paths and drops the rest (open redirect)", () => {
    expect(safeNextPath("/invitations")).toBe("/invitations");
    expect(safeNextPath("https://evil.example")).toBe("/members");
    expect(safeNextPath("//evil.example")).toBe("/members");
    expect(safeNextPath(null)).toBe("/members");
  });
});
