"use client";

import { UserMinus } from "lucide-react";

import { Avatar, RoleBadge } from "@/components/people";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { MemberRead, Role } from "@/lib/api/client";
import { canManage, grantableRoles, ROLE_LABELS } from "@/lib/roles";

type Props = {
  members: MemberRead[];
  actorRole: Role;
  actorUserId: string;
  busy: boolean;
  onChangeRole: (member: MemberRead, role: Role) => void;
  onRemove: (member: MemberRead) => void;
};

/** Members of the organization. Role and remove controls only where the API would allow them. */
export function MembersTable({ members, actorRole, actorUserId, busy, onChangeRole, onRemove }: Props) {
  const options = grantableRoles(actorRole);
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Persona</TableHead>
          <TableHead>Rol</TableHead>
          <TableHead>Miembro desde</TableHead>
          <TableHead className="text-right">
            <span className="sr-only">Acciones</span>
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {members.map((member) => {
          const manageable = canManage(actorRole, member.role);
          const isMe = member.user_id === actorUserId;
          return (
            <TableRow key={member.id}>
              <TableCell>
                <div className="flex items-center gap-3">
                  <Avatar email={member.email} />
                  <span className="font-medium">{member.email}</span>
                  {isMe && (
                    <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">vos</span>
                  )}
                </div>
              </TableCell>
              <TableCell>
                {manageable ? (
                  <NativeSelect
                    aria-label={`Rol de ${member.email}`}
                    value={member.role}
                    disabled={busy}
                    onChange={(event) => onChangeRole(member, event.target.value as Role)}
                  >
                    {Array.from(new Set([member.role, ...options])).map((role) => (
                      <option key={role} value={role}>
                        {ROLE_LABELS[role]}
                      </option>
                    ))}
                  </NativeSelect>
                ) : (
                  <RoleBadge role={member.role} />
                )}
              </TableCell>
              <TableCell className="text-muted-foreground">
                {new Date(member.created_at).toLocaleDateString("es-AR", { dateStyle: "medium" })}
              </TableCell>
              <TableCell className="text-right">
                {manageable && (
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={busy}
                    onClick={() => onRemove(member)}
                    className="text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                  >
                    <UserMinus />
                    {isMe ? "Salir de la organización" : "Quitar"}
                  </Button>
                )}
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
