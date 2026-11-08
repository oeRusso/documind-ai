"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ErrorMessage, Field } from "@/components/form";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, errorMessage, inOrganization, unwrap, type Role } from "@/lib/api/client";
import { useActiveOrganization } from "@/lib/organizations";
import { canManageMembers, invitableRoles, ROLE_LABELS } from "@/lib/roles";

const STATUS_LABELS: Record<string, string> = {
  pending: "Pendiente",
  expired: "Vencida",
  accepted: "Aceptada",
  revoked: "Revocada",
};

export default function InvitationsPage() {
  const { organization } = useActiveOrganization();
  const queryClient = useQueryClient();
  const organizationId = organization?.id ?? "";
  const key = ["invitations", organizationId];
  const allowed = organization ? canManageMembers(organization.role) : false;
  const [link, setLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const invitations = useQuery({
    queryKey: key,
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/invitations", { params: inOrganization(organizationId) }))
        .items,
    enabled: allowed,
  });

  const create = useMutation({
    mutationFn: async (body: { email: string; role: "admin" | "member" | "viewer" }) =>
      unwrap(await api.POST("/api/v1/invitations", { params: inOrganization(organizationId), body })),
    onSuccess: async (created) => {
      setLink(created.link);
      setCopied(false);
      await queryClient.invalidateQueries({ queryKey: key });
    },
  });

  const revoke = useMutation({
    mutationFn: async (id: string) =>
      unwrap(
        await api.DELETE("/api/v1/invitations/{invitation_id}", {
          params: { ...inOrganization(organizationId), path: { invitation_id: id } },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: key }),
  });

  if (!organization) return null;
  if (!allowed) {
    return <Alert>Tu rol en esta organización no permite gestionar invitaciones.</Alert>;
  }
  const roles = invitableRoles(organization.role);

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    create.mutate({
      email: String(form.get("email")),
      role: String(form.get("role")) as "admin" | "member" | "viewer",
    });
    event.currentTarget.reset();
  }

  return (
    <div className="grid gap-6">
      <Card>
        <CardHeader>
          <CardTitle>Invitar a {organization.name}</CardTitle>
          <CardDescription>
            La persona recibe un email con un link que vence en 7 días. También podés copiarlo y mandárselo vos.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
            <div className="min-w-64 flex-1">
              <Field id="email" label="Email" type="email" required />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="role">Rol</Label>
              <NativeSelect id="role" name="role" defaultValue={roles.includes("member") ? "member" : roles[0]}>
                {roles.map((role: Role) => (
                  <option key={role} value={role}>
                    {ROLE_LABELS[role]}
                  </option>
                ))}
              </NativeSelect>
            </div>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? "Invitando…" : "Invitar"}
            </Button>
          </form>
          <ErrorMessage message={create.error ? errorMessage(create.error) : null} />
          {link && (
            <Alert className="grid gap-2">
              <p>Invitación creada. Este link se muestra una sola vez:</p>
              <code className="break-all rounded bg-muted p-2 text-xs">{link}</code>
              <Button
                variant="outline"
                size="sm"
                className="w-fit"
                onClick={async () => {
                  await navigator.clipboard.writeText(link);
                  setCopied(true);
                }}
              >
                {copied ? "¡Copiado!" : "Copiar link"}
              </Button>
            </Alert>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Invitaciones abiertas</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4">
          <ErrorMessage
            message={invitations.error || revoke.error ? errorMessage(invitations.error ?? revoke.error) : null}
          />
          {invitations.data?.length === 0 && (
            <p className="text-sm text-muted-foreground">No hay invitaciones abiertas.</p>
          )}
          {invitations.data && invitations.data.length > 0 && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Email</TableHead>
                  <TableHead>Rol</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead>Vence</TableHead>
                  <TableHead className="text-right">Acciones</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {invitations.data.map((invitation) => (
                  <TableRow key={invitation.id}>
                    <TableCell>{invitation.email}</TableCell>
                    <TableCell>{ROLE_LABELS[invitation.role]}</TableCell>
                    <TableCell>
                      <Badge variant={invitation.status === "pending" ? "secondary" : "outline"}>
                        {STATUS_LABELS[invitation.status] ?? invitation.status}
                      </Badge>
                    </TableCell>
                    <TableCell>{new Date(invitation.expires_at).toLocaleDateString("es-AR")}</TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={revoke.isPending}
                        onClick={() => revoke.mutate(invitation.id)}
                      >
                        Revocar
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
