"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { DemoLoginButton } from "@/components/demo";
import { PublicPage } from "@/components/form";
import { LoginForm } from "@/components/login-form";
import { safeNextPath } from "@/lib/auth";

function Login() {
  const router = useRouter();
  const next = safeNextPath(useSearchParams().get("next"));
  return (
    <div className="grid gap-6">
      <LoginForm onLoggedIn={() => router.replace(next)} />
      <DemoLoginButton onLoggedIn={() => router.replace("/ask")} />
    </div>
  );
}

export default function LoginPage() {
  return (
    <PublicPage
      title="Bienvenido de nuevo"
      description="Entrá con tu email y tu contraseña."
      footer={
        <>
          ¿No tenés cuenta?{" "}
          <Link href="/register" className="font-medium text-primary hover:underline">
            Creá una para tu empresa
          </Link>
        </>
      }
    >
      <Suspense>
        <Login />
      </Suspense>
    </PublicPage>
  );
}
