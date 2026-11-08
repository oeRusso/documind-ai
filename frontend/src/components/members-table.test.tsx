import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { MemberRead } from "@/lib/api/client";

import { MembersTable } from "./members-table";

const member = (email: string, role: MemberRead["role"]): MemberRead => ({
  id: `m-${email}`,
  user_id: `u-${email}`,
  email,
  role,
  created_at: "2026-11-08T12:00:00Z",
});

const MEMBERS = [
  member("ana@acme.test", "owner"),
  member("carla@acme.test", "admin"),
  member("bob@acme.test", "viewer"),
];

function renderAs(actorRole: MemberRead["role"], onChangeRole = vi.fn(), onRemove = vi.fn()) {
  render(
    <MembersTable
      members={MEMBERS}
      actorRole={actorRole}
      actorUserId="u-carla@acme.test"
      busy={false}
      onChangeRole={onChangeRole}
      onRemove={onRemove}
    />,
  );
  return { onChangeRole, onRemove };
}

describe("MembersTable", () => {
  it("a viewer sees the members but no admin controls", () => {
    renderAs("viewer");

    expect(screen.getByText("ana@acme.test")).toBeInTheDocument();
    expect(screen.queryAllByRole("combobox")).toHaveLength(0);
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("an admin can only manage roles below admin", () => {
    renderAs("admin");

    expect(screen.getAllByRole("combobox")).toHaveLength(1); // only bob, the viewer
    const select = screen.getByRole("combobox", { name: "Rol de bob@acme.test" });
    const options = within(select).getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["Lector", "Miembro"]);
  });

  it("changing a role reports the member and the new role", async () => {
    const { onChangeRole } = renderAs("owner");

    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Rol de bob@acme.test" }), "member");

    expect(onChangeRole).toHaveBeenCalledWith(MEMBERS[2], "member");
  });
});
