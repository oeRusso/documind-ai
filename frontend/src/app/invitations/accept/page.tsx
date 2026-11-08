"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState, useSyncExternalStore } from "react";

import { ErrorMessage, Field, PublicPage } from "@/components/form";
import { Honeypot } from "@/components/honeypot";
import { LoginForm } from "@/components/login-form";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import { setActiveOrganizationId } from "@/lib/api/organization-store";
import { useAuth } from "@/lib/auth";
import { parseInvitationHash, type InvitationLink } from "@/lib/invitation-link";
import { ORGANIZATIONS_KEY } from "@/lib/organizations";

// Read the link once and take the token out of the address bar (and so out of the history).
let captured: InvitationLink | null | undefined;
function captureLink(): InvitationLink | null {
  if (captured === undefined) {
    captured = parseInvitationHash(window.location.hash);
    if (captured) window.history.replaceState(null, "", window.location.pathname);
  }
  return captured;
}
const noSubscription = () => () => {};

export default function AcceptInvitationPage() {
  const link = useSyncExternalStore(noSubscription, captureLink, () => undefined);
  return (
    <PublicPage>
      <Card>
        <CardHeader>
          <CardTitle>Invitación</CardTitle>
          <CardDescription>Te invitaron a una organización en DocuMind AI.</CardDescription>
        </CardHeader>
        <CardContent>
          {link === undefined ? null : link === null ? (
            <ErrorMessage message="El link de invitación está incompleto. Pedí que te lo vuelvan a mandar." />
          ) : (
            <Accept link={link} />
          )}
        </CardContent>
      </Card>
    </PublicPage>
  );
}

function Accept({ link }: { link: InvitationLink }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { status, user, startSession, logout } = useAuth();
  const [mode, setMode] = useState<"register" | "login">("register");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function enter(organizationId: string) {
    setActiveOrganizationId(organizationId);
    await queryClient.invalidateQueries({ queryKey: ORGANIZATIONS_KEY });
    router.replace("/members");
  }

  async function run(action: () => Promise<void>) {
    setPending(true);
    setError(null);
    try {
      await action();
    } catch (exception) {
      setError(errorMessage(exception));
    } finally {
      setPending(false);
    }
  }

  const accept = () =>
    run(async () => {
      const organization = unwrap(
        await api.POST("/api/v1/invitations/accept", {
          body: { organization_id: link.organizationId, token: link.token },
        }),
      );
      await enter(organization.id);
    });

  if (status === "loading") return <p className="text-sm text-muted-foreground">Cargando…</p>;

  if (status === "authenticated" && user) {
    return (
      <div className="grid gap-4">
        <p className="text-sm">
          Vas a aceptar la invitación como <strong>{user.email}</strong>.
        </p>
        <ErrorMessage message={error} />
        <Button onClick={accept} disabled={pending}>
          {pending ? "Aceptando…" : "Aceptar invitación"}
        </Button>
        <Button variant="ghost" onClick={() => void logout()}>
          No soy yo: cerrar sesión
        </Button>
      </div>
    );
  }

  if (mode === "login") {
    return (
      <div className="grid gap-4">
        <LoginForm onLoggedIn={accept} />
        <ErrorMessage message={error} />
        <Button variant="link" onClick={() => setMode("register")}>
          No tengo cuenta: crear una
        </Button>
      </div>
    );
  }

  async function register(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await run(async () => {
      const tokens = unwrap(
        await api.POST("/api/v1/auth/register", {
          body: {
            email: String(form.get("email")),
            password: String(form.get("password")),
            invitation: { organization_id: link.organizationId, token: link.token },
            website: String(form.get("website") ?? ""),
          },
        }),
      );
      await startSession(tokens.access_token);
      await enter(link.organizationId);
    });
  }

  return (
    <form onSubmit={register} className="relative grid gap-4">
      <p className="text-sm text-muted-foreground">Creá tu cuenta con el email que recibió la invitación.</p>
      <Field id="email" label="Email" type="email" autoComplete="email" required />
      <Field
        id="password"
        label="Contraseña (10 caracteres o más)"
        type="password"
        autoComplete="new-password"
        minLength={10}
        required
      />
      <Honeypot />
      <ErrorMessage message={error} />
      <Button type="submit" disabled={pending}>
        {pending ? "Creando…" : "Crear cuenta y unirme"}
      </Button>
      <Button type="button" variant="link" onClick={() => setMode("login")}>
        Ya tengo cuenta
      </Button>
    </form>
  );
}
