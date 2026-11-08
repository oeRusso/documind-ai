import { AlertCircle } from "lucide-react";

import { BrandBanner, BrandPanel } from "@/components/brand";
import { Alert } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function Field({
  id,
  label,
  hint,
  ...props
}: { id: string; label: string; hint?: string } & React.ComponentProps<typeof Input>) {
  return (
    <div className="grid gap-2">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} name={id} {...props} />
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

export function ErrorMessage({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <Alert variant="destructive" className="flex items-start gap-2">
      <AlertCircle className="mt-0.5 size-4 shrink-0" />
      <span>{message}</span>
    </Alert>
  );
}

/**
 * Public pages (login, register, invitation): the brand panel on the left on wide screens and
 * the form on the right.
 */
export function PublicPage({
  title,
  description,
  footer,
  children,
}: {
  title: string;
  description?: React.ReactNode;
  footer?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="grid min-h-screen lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
      <BrandPanel />
      <main className="flex items-center justify-center px-4 py-8 sm:px-8 lg:py-12">
        <div className="relative w-full max-w-sm">
          <BrandBanner />
          <h1 className="text-2xl font-semibold">{title}</h1>
          {description && <p className="mt-2 text-sm text-muted-foreground">{description}</p>}
          <div className="mt-8">{children}</div>
          {footer && <div className="mt-8 text-sm text-muted-foreground">{footer}</div>}
        </div>
      </main>
    </div>
  );
}
