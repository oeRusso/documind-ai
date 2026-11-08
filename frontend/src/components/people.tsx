import type { Role } from "@/lib/api/client";
import { ROLE_LABELS } from "@/lib/roles";
import { cn } from "@/lib/utils";

const AVATAR_COLORS = [
  "bg-indigo-500/15 text-indigo-700 dark:text-indigo-300",
  "bg-sky-500/15 text-sky-700 dark:text-sky-300",
  "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  "bg-amber-500/15 text-amber-700 dark:text-amber-300",
  "bg-rose-500/15 text-rose-700 dark:text-rose-300",
  "bg-violet-500/15 text-violet-700 dark:text-violet-300",
];

/** Two letters from the email, on a color that is always the same for that email. */
export function Avatar({ email, className }: { email: string; className?: string }) {
  const name = email.split("@")[0] ?? email;
  const initials = name.slice(0, 2).toUpperCase();
  const hash = Array.from(email).reduce((sum, char) => sum + char.charCodeAt(0), 0);
  return (
    <span
      aria-hidden="true"
      className={cn(
        "grid size-8 shrink-0 place-items-center rounded-full text-xs font-semibold",
        AVATAR_COLORS[hash % AVATAR_COLORS.length],
        className,
      )}
    >
      {initials}
    </span>
  );
}

const ROLE_STYLES: Record<Role, string> = {
  owner: "bg-primary/10 text-primary ring-primary/20",
  admin: "bg-sky-500/10 text-sky-700 ring-sky-500/20 dark:text-sky-300",
  member: "bg-emerald-500/10 text-emerald-700 ring-emerald-500/20 dark:text-emerald-300",
  viewer: "bg-muted text-muted-foreground ring-border",
};

export function RoleBadge({ role, className }: { role: Role; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex w-fit items-center rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset",
        ROLE_STYLES[role],
        className,
      )}
    >
      {ROLE_LABELS[role]}
    </span>
  );
}

/** Title, one line of context and, optionally, actions on the right. */
export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold">{title}</h1>
        {description && <p className="mt-1.5 text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions}
    </div>
  );
}
