"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/lib/auth";

/** Private area: without a session, go to /login and come back afterwards. */
export default function PrivateLayout({ children }: { children: React.ReactNode }) {
  const { status } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (status === "anonymous") router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [status, router, pathname]);

  if (status !== "authenticated") {
    return <p className="p-8 text-sm text-muted-foreground">Cargando…</p>;
  }
  return <AppShell>{children}</AppShell>;
}
