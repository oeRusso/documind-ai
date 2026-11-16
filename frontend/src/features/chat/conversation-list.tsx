"use client";

/** The person's conversations in the active organization, newest first (stage 8). */

import { useInfiniteQuery } from "@tanstack/react-query";
import { MessageSquarePlus } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { api, inOrganization, unwrap } from "@/lib/api/client";
import { cn } from "@/lib/utils";

export function conversationsKey(organizationId: string) {
  return ["conversations", organizationId];
}

/** "14:10" today, "16 nov" this year, "16 nov 2025" before. */
export function shortWhen(iso: string, now = new Date()): string {
  const date = new Date(iso);
  if (date.toDateString() === now.toDateString()) {
    return date.toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
  }
  const month = date.toLocaleDateString("es-AR", { month: "short" }).replace(".", "");
  const year = date.getFullYear() === now.getFullYear() ? "" : ` ${date.getFullYear()}`;
  return `${date.getDate()} ${month}${year}`;
}

export function ConversationList({
  organizationId,
  activeId,
}: {
  organizationId: string;
  activeId: string | null;
}) {
  const conversations = useInfiniteQuery({
    queryKey: conversationsKey(organizationId),
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) =>
      unwrap(
        await api.GET("/api/v1/conversations", {
          params: { ...inOrganization(organizationId), query: { limit: 30, cursor: pageParam } },
        }),
      ),
    getNextPageParam: (last) => last.next_cursor ?? null,
  });
  const items = conversations.data?.pages.flatMap((page) => page.items) ?? [];

  // minmax(0,1fr): without it the longest title widens the column and pushes the chat aside.
  return (
    <nav aria-label="Conversaciones" className="grid min-w-0 grid-cols-[minmax(0,1fr)] content-start gap-2">
      <Button asChild variant={activeId ? "outline" : "default"} className="justify-start">
        <Link href="/ask">
          <MessageSquarePlus />
          Nueva conversación
        </Link>
      </Button>
      {items.length > 0 && (
        <p className="mt-2 px-2 text-[11px] font-semibold tracking-wider text-muted-foreground/70 uppercase">
          Historial
        </p>
      )}
      <ul className="grid grid-cols-[minmax(0,1fr)] gap-0.5">
        {items.map((conversation) => (
          <li key={conversation.id}>
            <Link
              href={`/ask?c=${conversation.id}`}
              aria-current={conversation.id === activeId ? "page" : undefined}
              className={cn(
                "grid rounded-lg px-3 py-2 text-sm transition-colors hover:bg-muted",
                conversation.id === activeId && "bg-muted",
              )}
              title={conversation.title ?? "Sin preguntas todavía"}
            >
              <span className={cn("truncate", conversation.id === activeId && "font-medium")}>
                {conversation.title ?? <span className="text-muted-foreground italic">Sin preguntas</span>}
              </span>
              <span className="text-xs text-muted-foreground">{shortWhen(conversation.updated_at)}</span>
            </Link>
          </li>
        ))}
      </ul>
      {conversations.hasNextPage && (
        <Button variant="ghost" size="sm" onClick={() => void conversations.fetchNextPage()}>
          Ver más
        </Button>
      )}
    </nav>
  );
}
