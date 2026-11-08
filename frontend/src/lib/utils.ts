import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Join Tailwind classes, letting later ones win (shadcn/ui helper). */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
