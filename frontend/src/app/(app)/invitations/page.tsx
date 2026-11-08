"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, CheckCircle2, Clock, Copy, Mail, Send, X } from "lucide-react";
import { useState } from "react";

import { ErrorMessage, Field } from "@/components/form";
import { PageHeader, RoleBadge } from "@/components/people";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, errorMessage, inOrganization, unwrap, type Role } from "@/lib/api/client";
import { useActiveOrganization } from "@/lib/organizations";
import { canManageMembers, invitableRoles, ROLE_LABELS } from "@/lib/roles";
import { cn } from "@/lib/utils";

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
    <>
      <PageHeader
        title="Invitaciones"
        description={
          <>
            Sumá personas a <strong className="font-medium text-foreground">{organization.name}</strong>: les llega
            un email con un link que vence en 7 días.
          </>
        }
      />
      <div className="grid gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Send className="size-4 text-primary" />
              Nueva invitación
            </CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4">
            <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
              <div className="min-w-64 flex-1">
                <Field id="email" label="Email" type="email" placeholder="persona@empresa.com" required />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="role">Rol</Label>
                <NativeSelect
                  id="role"
                  name="role"
                  className="h-10"
                  defaultValue={roles.includes("member") ? "member" : roles[0]}
                >
                  {roles.map((role: Role) => (
                    <option key={role} value={role}>
                      {ROLE_LABELS[role]}
                    </option>
                  ))}
                </NativeSelect>
              </div>
              <Button type="submit" className="h-10" disabled={create.isPending}>
                {create.isPending ? "Invitando…" : "Invitar"}
              </Button>
            </form>
            <ErrorMessage message={create.error ? errorMessage(create.error) : null} />
            {link && (
              <div className="grid gap-3 rounded-xl border border-success/30 bg-success/5 p-4 text-sm">
                <p className="flex items-center gap-2 font-medium">
                  <CheckCircle2 className="size-4 text-success" />
                  Invitación creada. Este link se muestra una sola vez:
                </p>
                <code className="rounded-lg border bg-card p-3 text-xs break-all">{link}</code>
                <Button
                  variant="outline"
                  size="sm"
                  className="w-fit"
                  onClick={async () => {
                    await navigator.clipboard.writeText(link);
                    setCopied(true);
                  }}
                >
                  {copied ? <Check /> : <Copy />}
                  {copied ? "¡Copiado!" : "Copiar link"}
                </Button>
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="gap-0 overflow-hidden pb-0">
          <CardHeader className="pb-6">
            <CardTitle>Invitaciones abiertas</CardTitle>
          </CardHeader>
          <div className="px-6 empty:hidden [&:has(>*)]:pb-4">
            <ErrorMessage
              message={invitations.error || revoke.error ? errorMessage(invitations.error ?? revoke.error) : null}
            />
          </div>
          {invitations.data?.length === 0 && (
            <div className="grid place-items-center gap-2 border-t px-6 py-10 text-center text-sm text-muted-foreground">
              <Mail className="size-6 opacity-50" />
              No hay invitaciones abiertas.
            </div>
          )}
          {invitations.data && invitations.data.length > 0 && (
            <div className="border-t">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Email</TableHead>
                    <TableHead>Rol</TableHead>
                    <TableHead>Estado</TableHead>
                    <TableHead>Vence</TableHead>
                    <TableHead className="text-right">
                      <span className="sr-only">Acciones</span>
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {invitations.data.map((invitation) => (
                    <TableRow key={invitation.id}>
                      <TableCell className="font-medium">{invitation.email}</TableCell>
                      <TableCell>
                        <RoleBadge role={invitation.role} />
                      </TableCell>
                      <TableCell>
                        <span
                          className={cn(
                            "inline-flex items-center gap-1.5 text-xs font-medium",
                            invitation.status === "pending" ? "text-warning" : "text-muted-foreground",
                          )}
                        >
                          <Clock className="size-3.5" />
                          {STATUS_LABELS[invitation.status] ?? invitation.status}
                        </span>
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {new Date(invitation.expires_at).toLocaleDateString("es-AR", { dateStyle: "medium" })}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={revoke.isPending}
                          onClick={() => revoke.mutate(invitation.id)}
                          className="text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                        >
                          <X />
                          Revocar
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
