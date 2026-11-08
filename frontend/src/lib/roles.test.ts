import { describe, expect, it } from "vitest";

import { canGrant, canManage, grantableRoles, invitableRoles } from "./roles";

// Same table as backend/tests/unit/test_permissions.py: the UI must not offer what the API refuses.
describe("role rules", () => {
  it("viewers and members manage nobody", () => {
    expect(canManage("viewer", "viewer")).toBe(false);
    expect(canManage("member", "viewer")).toBe(false);
    expect(grantableRoles("member")).toEqual([]);
    expect(invitableRoles("viewer")).toEqual([]);
  });

  it("admins manage and grant only roles below their own", () => {
    expect(canManage("admin", "member")).toBe(true);
    expect(canManage("admin", "admin")).toBe(false);
    expect(canManage("admin", "owner")).toBe(false);
    expect(canGrant("admin", "admin")).toBe(false);
    expect(invitableRoles("admin")).toEqual(["member", "viewer"]);
  });

  it("owners manage everyone and never invite owners", () => {
    expect(canManage("owner", "owner")).toBe(true);
    expect(grantableRoles("owner")).toEqual(["owner", "admin", "member", "viewer"]);
    expect(invitableRoles("owner")).toEqual(["admin", "member", "viewer"]);
  });
});
