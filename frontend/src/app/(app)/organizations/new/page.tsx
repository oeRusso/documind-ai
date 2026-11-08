"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ErrorMessage, Field } from "@/components/form";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import { setActiveOrganizationId } from "@/lib/api/organization-store";
import { ORGANIZATIONS_KEY } from "@/lib/organizations";
import { slugify } from "@/lib/slug";

export default function NewOrganizationPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugEdited, setSlugEdited] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      const organization = unwrap(await api.POST("/api/v1/organizations", { body: { name, slug } }));
      setActiveOrganizationId(organization.id);
      await queryClient.invalidateQueries({ queryKey: ORGANIZATIONS_KEY });
      router.replace("/members");
    } catch (exception) {
      setError(errorMessage(exception));
    } finally {
      setPending(false);
    }
  }

  return (
    <Card className="max-w-lg">
      <CardHeader>
        <CardTitle>Nueva organización</CardTitle>
        <CardDescription>Vas a ser su owner. Sus datos quedan separados de las demás.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid gap-4">
          <Field
            id="name"
            label="Nombre"
            value={name}
            onChange={(event) => {
              setName(event.target.value);
              if (!slugEdited) setSlug(slugify(event.target.value));
            }}
            required
          />
          <Field
            id="slug"
            label="Identificador (slug)"
            value={slug}
            onChange={(event) => {
              setSlugEdited(true);
              setSlug(event.target.value);
            }}
            pattern="[a-z0-9-]{2,63}"
            title="Minúsculas, números y guiones"
            required
          />
          <ErrorMessage message={error} />
          <Button type="submit" disabled={pending} className="w-fit">
            {pending ? "Creando…" : "Crear organización"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
