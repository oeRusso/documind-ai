"use client";

// shadcn/ui (MIT): https://ui.shadcn.com/docs/components/label
import * as LabelPrimitive from "@radix-ui/react-label";
import * as React from "react";

import { cn } from "@/lib/utils";

function Label({ className, ...props }: React.ComponentProps<typeof LabelPrimitive.Root>) {
  return (
    <LabelPrimitive.Root
      data-slot="label"
      className={cn("flex items-center gap-2 text-sm font-medium leading-none select-none", className)}
      {...props}
    />
  );
}

export { Label };
