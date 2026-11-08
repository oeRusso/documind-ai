/**
 * Role rules for the UI: they only decide which buttons to show. The API enforces the real
 * rules (backend/app/modules/organizations/domain/permissions.py) and answers 403 anyway.
 */

import type { Role } from "@/lib/api/client";

export const ROLE_LABELS: Record<Role, string> = {
  owner: "Owner",
  admin: "Administrador",
  member: "Miembro",
  viewer: "Lector",
};

const RANK: Record<Role, number> = { viewer: 0, member: 1, admin: 2, owner: 3 };
export const ROLES: Role[] = ["owner", "admin", "member", "viewer"];
export const INVITABLE_ROLES: Role[] = ["admin", "member", "viewer"];

export function canManageMembers(actor: Role): boolean {
  return actor === "owner" || actor === "admin";
}

/** Can `actor` change the role of, or remove, someone who has `target`? */
export function canManage(actor: Role, target: Role): boolean {
  return canManageMembers(actor) && (actor === "owner" || RANK[target] < RANK[actor]);
}

/** Can `actor` give `role` to someone? */
export function canGrant(actor: Role, role: Role): boolean {
  return canManageMembers(actor) && (actor === "owner" || RANK[role] < RANK[actor]);
}

export function grantableRoles(actor: Role): Role[] {
  return ROLES.filter((role) => canGrant(actor, role));
}

export function invitableRoles(actor: Role): Role[] {
  return INVITABLE_ROLES.filter((role) => canGrant(actor, role));
}
