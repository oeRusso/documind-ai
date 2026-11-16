"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ErrorMessage, Field, PublicPage } from "@/components/form";
import { Honeypot } from "@/components/honeypot";
import { Button } from "@/components/ui/button";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import { useAuth } from "@/lib/auth";
import { slugify } from "@/lib/slug";

export default function RegisterPage() {
  const router = useRouter();
  const { startSession } = useAuth();
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugEdited, setSlugEdited] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setPending(true);
    setError(null);
    try {
      const tokens = unwrap(
        await api.POST("/api/v1/auth/register", {
          body: {
            email: String(form.get("email")),
            password: String(form.get("password")),
            organization_name: name,
            organization_slug: slug,
            website: String(form.get("website") ?? ""),
          },
        }),
      );
      await startSession(tokens.access_token);
      router.replace("/documents");
    } catch (exception) {
      setError(errorMessage(exception));
    } finally {
      setPending(false);
    }
  }

  return (
    <PublicPage
      title="Creá tu cuenta"
      description="Creás tu usuario y el espacio de tu empresa. Vas a ser su owner."
      footer={
        <>
          ¿Ya tenés cuenta?{" "}
          <Link href="/login" className="font-medium text-primary hover:underline">
            Iniciá sesión
          </Link>
        </>
      }
    >
      <form onSubmit={submit} className="relative grid gap-5">
        <Field id="email" label="Email" type="email" autoComplete="email" placeholder="vos@empresa.com" required />
        <Field
          id="password"
          label="Contraseña"
          hint="10 caracteres o más."
          type="password"
          autoComplete="new-password"
          minLength={10}
          required
        />
        <div className="grid gap-5 rounded-xl border bg-card p-4">
          <Field
            id="organization_name"
            label="Nombre de la empresa"
            placeholder="Acme S.A."
            value={name}
            onChange={(event) => {
              setName(event.target.value);
              if (!slugEdited) setSlug(slugify(event.target.value));
            }}
            required
          />
          <Field
            id="organization_slug"
            label="Identificador"
            hint="Minúsculas, números y guiones. Se completa solo."
            value={slug}
            onChange={(event) => {
              setSlugEdited(true);
              setSlug(event.target.value);
            }}
            pattern="[a-z0-9-]{2,63}"
            title="Minúsculas, números y guiones"
            required
          />
        </div>
        <Honeypot />
        <ErrorMessage message={error} />
        <Button type="submit" size="lg" disabled={pending}>
          {pending ? "Creando…" : "Crear cuenta"}
        </Button>
      </form>
    </PublicPage>
  );
}
