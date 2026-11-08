"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { PublicPage } from "@/components/form";
import { LoginForm } from "@/components/login-form";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { safeNextPath } from "@/lib/auth";

function Login() {
  const router = useRouter();
  const next = safeNextPath(useSearchParams().get("next"));
  return (
    <Card>
      <CardHeader>
        <CardTitle>Iniciar sesión</CardTitle>
        <CardDescription>Entrá con tu email y tu contraseña.</CardDescription>
      </CardHeader>
      <CardContent>
        <LoginForm onLoggedIn={() => router.replace(next)} />
      </CardContent>
      <CardFooter className="text-sm text-muted-foreground">
        ¿No tenés cuenta?&nbsp;
        <Link href="/register" className="underline">
          Registrate
        </Link>
      </CardFooter>
    </Card>
  );
}

export default function LoginPage() {
  return (
    <PublicPage>
      <Suspense>
        <Login />
      </Suspense>
    </PublicPage>
  );
}
