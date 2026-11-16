"use client";

/** The public demo (stage 12): the "Probar la demo" button and the notice inside the app. */

import { useQuery } from "@tanstack/react-query";
import { Info, Loader2, PlayCircle } from "lucide-react";
import { useState } from "react";

import { ErrorMessage } from "@/components/form";
import { Button } from "@/components/ui/button";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import { useAuth } from "@/lib/auth";

export const DEMO_SLUG = "demo-publica"; // backend/app/shared/demo.py

/** Shown only when the server has a demo (GET /api/v1/demo answers). */
export function DemoLoginButton({ onLoggedIn }: { onLoggedIn: () => void | Promise<void> }) {
  const { startSession } = useAuth();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const demo = useQuery({
    queryKey: ["demo-account"],
    queryFn: async () => unwrap(await api.GET("/api/v1/demo")),
    retry: false,
    staleTime: Infinity,
  });
  if (!demo.data) return null;
  const account = demo.data;

  async function enter() {
    setPending(true);
    setError(null);
    try {
      const tokens = unwrap(await api.POST("/api/v1/auth/login", { body: account }));
      await startSession(tokens.access_token);
      await onLoggedIn();
    } catch (exception) {
      setError(errorMessage(exception));
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="grid gap-2 rounded-xl border border-dashed p-4">
      <Button type="button" variant="outline" size="lg" onClick={() => void enter()} disabled={pending}>
        {pending ? <Loader2 className="animate-spin" /> : <PlayCircle />}
        Probar la demo sin registrarte
      </Button>
      <p className="text-xs text-muted-foreground">
        Solo lectura, con leyes argentinas de ejemplo. Tus preguntas se borran cada noche: no escribas datos
        personales.
      </p>
      <ErrorMessage message={error} />
    </div>
  );
}

export function DemoNotice() {
  return (
    <div className="mb-6 flex items-start gap-2 rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100">
      <Info className="mt-0.5 size-4 shrink-0" />
      <p>
        Estás en la <strong>demo pública</strong>: solo lectura y con un límite de preguntas. Tu historial lo ves
        solo vos y se borra cada noche; igual, no escribas datos personales.
      </p>
    </div>
  );
}
