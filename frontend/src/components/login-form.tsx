"use client";

import { Loader2 } from "lucide-react";
import { useState } from "react";

import { ErrorMessage, Field } from "@/components/form";
import { Button } from "@/components/ui/button";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import { useAuth } from "@/lib/auth";

/** Email + password. Calls `onLoggedIn` once the session is started. */
export function LoginForm({ onLoggedIn }: { onLoggedIn: () => void | Promise<void> }) {
  const { startSession } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setPending(true);
    setError(null);
    try {
      const body = { email: String(form.get("email")), password: String(form.get("password")) };
      const tokens = unwrap(await api.POST("/api/v1/auth/login", { body }));
      await startSession(tokens.access_token);
      await onLoggedIn();
    } catch (exception) {
      setError(errorMessage(exception));
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-5">
      <Field id="email" label="Email" type="email" autoComplete="email" placeholder="vos@empresa.com" required />
      <Field id="password" label="Contraseña" type="password" autoComplete="current-password" required />
      <ErrorMessage message={error} />
      <Button type="submit" size="lg" disabled={pending}>
        {pending && <Loader2 className="animate-spin" />}
        {pending ? "Entrando…" : "Entrar"}
      </Button>
    </form>
  );
}
