"use client";

import {
  Building2,
  FileText,
  History,
  LogOut,
  Mail,
  MessageSquare,
  Plus,
  Search,
  Users,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { Logo } from "@/components/brand";
import { Avatar, RoleBadge } from "@/components/people";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import { useAuth } from "@/lib/auth";
import { useActiveOrganization } from "@/lib/organizations";
import { canManageMembers } from "@/lib/roles";
import { cn } from "@/lib/utils";

type NavItem = { href: string; label: string; icon: LucideIcon; show: boolean };

/** What the next stages add, shown greyed out so the menu tells where the product is going. */
const COMING_SOON = [{ label: "Conversaciones", icon: History, stage: "Etapa 8" }];

function OrganizationSwitcher({ id }: { id: string }) {
  const { organization, organizations, select } = useActiveOrganization();
  return (
    <div className="grid gap-2 rounded-xl border bg-card p-3">
      <label htmlFor={id} className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <Building2 className="size-3.5" />
        Organización
      </label>
      <NativeSelect
        id={id}
        className="w-full font-medium"
        value={organization?.id ?? ""}
        onChange={(event) => select(event.target.value)}
      >
        {organizations.map((o) => (
          <option key={o.id} value={o.id}>
            {o.name}
          </option>
        ))}
      </NativeSelect>
      {organization && <RoleBadge role={organization.role} />}
    </div>
  );
}

function NavLinks({ items, compact = false }: { items: NavItem[]; compact?: boolean }) {
  const pathname = usePathname();
  return items
    .filter((item) => item.show)
    .map(({ href, label, icon: Icon }) => {
      const active = pathname === href || pathname.startsWith(`${href}/`);
      return (
        <Link
          key={href}
          href={href}
          aria-current={active ? "page" : undefined}
          className={cn(
            "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium whitespace-nowrap text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground",
            active && "bg-accent text-accent-foreground",
            compact && "py-1.5",
          )}
        >
          <Icon className="size-4" />
          {label}
        </Link>
      );
    });
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { user, logout } = useAuth();
  const { organization } = useActiveOrganization();

  const items: NavItem[] = [
    { href: "/documents", label: "Documentos", icon: FileText, show: true },
    { href: "/ask", label: "Preguntar", icon: MessageSquare, show: true },
    { href: "/search", label: "Búsqueda", icon: Search, show: true },
    { href: "/members", label: "Miembros", icon: Users, show: true },
    {
      href: "/invitations",
      label: "Invitaciones",
      icon: Mail,
      show: organization ? canManageMembers(organization.role) : false,
    },
    { href: "/organizations/new", label: "Nueva organización", icon: Plus, show: true },
  ];

  async function signOut() {
    await logout();
    router.replace("/login");
  }

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[17rem_minmax(0,1fr)]">
      <aside className="sticky top-0 hidden h-screen flex-col gap-6 border-r bg-sidebar p-4 lg:flex">
        <Link href="/documents" className="px-2 pt-1">
          <Logo />
        </Link>
        <OrganizationSwitcher id="organization" />
        <nav aria-label="Principal" className="grid gap-1">
          <NavLinks items={items} />
        </nav>
        <div className="grid gap-1">
          <p className="px-3 pb-1 text-[11px] font-semibold tracking-wider text-muted-foreground/70 uppercase">
            Próximamente
          </p>
          {COMING_SOON.map(({ label, icon: Icon, stage }) => (
            <span
              key={label}
              aria-disabled="true"
              className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-muted-foreground/60"
            >
              <Icon className="size-4" />
              {label}
              <span className="ml-auto rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium">{stage}</span>
            </span>
          ))}
        </div>
        <div className="mt-auto flex items-center gap-3 rounded-xl border bg-card p-3">
          {user && <Avatar email={user.email} />}
          <span className="min-w-0 flex-1 truncate text-sm font-medium" title={user?.email}>
            {user?.email}
          </span>
          <Button variant="ghost" size="sm" onClick={signOut} className="px-2 text-muted-foreground">
            <LogOut />
            Salir
          </Button>
        </div>
      </aside>

      <div className="min-w-0">
        <header className="sticky top-0 z-10 border-b bg-background/85 backdrop-blur lg:hidden">
          <div className="flex items-center gap-3 px-4 py-3">
            <Link href="/documents">
              <Logo />
            </Link>
            <Button variant="ghost" size="sm" onClick={signOut} className="ml-auto text-muted-foreground">
              <LogOut />
              Salir
            </Button>
          </div>
          <nav aria-label="Principal" className="flex gap-1 overflow-x-auto px-3 pb-2 [scrollbar-width:none]">
            <NavLinks items={items} compact />
          </nav>
        </header>
        <main className="mx-auto max-w-5xl px-4 py-8 sm:px-8 lg:py-12">
          <div className="mb-6 lg:hidden">
            <OrganizationSwitcher id="organization-mobile" />
          </div>
          {children}
        </main>
      </div>
    </div>
  );
}
