"use client";

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
          <TableHead>Email</TableHead>
          <TableHead>Rol</TableHead>
          <TableHead>Desde</TableHead>
          <TableHead className="text-right">Acciones</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {members.map((member) => {
          const manageable = canManage(actorRole, member.role);
          const isMe = member.user_id === actorUserId;
          return (
            <TableRow key={member.id}>
              <TableCell>
                {member.email}
                {isMe && <span className="ml-2 text-xs text-muted-foreground">(vos)</span>}
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
                  ROLE_LABELS[member.role]
                )}
              </TableCell>
              <TableCell>{new Date(member.created_at).toLocaleDateString("es-AR")}</TableCell>
              <TableCell className="text-right">
                {manageable && (
                  <Button variant="outline" size="sm" disabled={busy} onClick={() => onRemove(member)}>
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
