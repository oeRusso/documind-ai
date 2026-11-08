"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { AppShell } from "@/components/app-shell";
import { LogoMark } from "@/components/brand";
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
    return (
      <div className="grid min-h-screen place-items-center">
        <LogoMark className="size-10 animate-pulse" />
        <span className="sr-only">Cargando…</span>
      </div>
    );
  }
  return <AppShell>{children}</AppShell>;
}
