"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ErrorMessage } from "@/components/form";
import { MembersTable } from "@/components/members-table";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api, errorMessage, inOrganization, unwrap, type MemberRead, type Role } from "@/lib/api/client";
import { useAuth } from "@/lib/auth";
import { ORGANIZATIONS_KEY, useActiveOrganization } from "@/lib/organizations";

export default function MembersPage() {
  const { user } = useAuth();
  const { organization } = useActiveOrganization();
  const queryClient = useQueryClient();
  const organizationId = organization?.id ?? "";
  const key = ["members", organizationId];

  const members = useQuery({
    queryKey: key,
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/members", { params: inOrganization(organizationId) })).items,
    enabled: Boolean(organization),
  });

  const refresh = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: key }),
      // Changing my own role (or leaving) changes what I can do here.
      queryClient.invalidateQueries({ queryKey: ORGANIZATIONS_KEY }),
    ]);

  const changeRole = useMutation({
    mutationFn: async ({ member, role }: { member: MemberRead; role: Role }) =>
      unwrap(
        await api.PATCH("/api/v1/members/{membership_id}", {
          params: { ...inOrganization(organizationId), path: { membership_id: member.id } },
          body: { role },
        }),
      ),
    onSuccess: refresh,
  });

  const remove = useMutation({
    mutationFn: async (member: MemberRead) =>
      unwrap(
        await api.DELETE("/api/v1/members/{membership_id}", {
          params: { ...inOrganization(organizationId), path: { membership_id: member.id } },
        }),
      ),
    onSuccess: refresh,
  });

  if (!organization || !user) return null;
  const error = members.error ?? changeRole.error ?? remove.error;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Miembros de {organization.name}</CardTitle>
        <CardDescription>Quién tiene acceso a esta organización y con qué rol.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        <ErrorMessage message={error ? errorMessage(error) : null} />
        {members.data && (
          <MembersTable
            members={members.data}
            actorRole={organization.role}
            actorUserId={user.id}
            busy={changeRole.isPending || remove.isPending}
            onChangeRole={(member, role) => changeRole.mutate({ member, role })}
            onRemove={(member) => {
              if (window.confirm(`¿Quitar a ${member.email} de ${organization.name}?`)) {
                remove.mutate(member);
              }
            }}
          />
        )}
      </CardContent>
    </Card>
  );
}
