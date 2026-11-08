"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import { useAuth } from "@/lib/auth";
import { useActiveOrganization } from "@/lib/organizations";
import { canManageMembers, ROLE_LABELS } from "@/lib/roles";
import { cn } from "@/lib/utils";

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const { organization, organizations, select } = useActiveOrganization();

  const links = [
    { href: "/members", label: "Miembros", show: true },
    {
      href: "/invitations",
      label: "Invitaciones",
      show: organization ? canManageMembers(organization.role) : false,
    },
  ];

  return (
    <div className="min-h-screen">
      <header className="border-b">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3">
          <Link href="/members" className="font-semibold">
            DocuMind AI
          </Link>
          <div className="flex items-center gap-2">
            <label htmlFor="organization" className="sr-only">
              Organización
            </label>
            <NativeSelect
              id="organization"
              value={organization?.id ?? ""}
              onChange={(event) => select(event.target.value)}
            >
              {organizations.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name}
                </option>
              ))}
            </NativeSelect>
            {organization && <Badge variant="secondary">{ROLE_LABELS[organization.role]}</Badge>}
          </div>
          <nav className="flex gap-1">
            {links
              .filter((link) => link.show)
              .map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  className={cn(
                    "rounded-md px-3 py-1.5 text-sm hover:bg-accent",
                    pathname === link.href && "bg-accent font-medium",
                  )}
                >
                  {link.label}
                </Link>
              ))}
            <Link href="/organizations/new" className="rounded-md px-3 py-1.5 text-sm hover:bg-accent">
              Nueva organización
            </Link>
          </nav>
          <div className="ml-auto flex items-center gap-3 text-sm text-muted-foreground">
            <span>{user?.email}</span>
            <Button
              variant="outline"
              size="sm"
              onClick={async () => {
                await logout();
                router.replace("/login");
              }}
            >
              Salir
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-8">{children}</main>
    </div>
  );
}
