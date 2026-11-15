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

  return (
    <nav aria-label="Conversaciones" className="grid content-start gap-2">
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
      <ul className="grid gap-0.5">
        {items.map((conversation) => (
          <li key={conversation.id}>
            <Link
              href={`/ask?c=${conversation.id}`}
              aria-current={conversation.id === activeId ? "page" : undefined}
              className={cn(
                "block truncate rounded-lg px-3 py-2 text-sm hover:bg-muted",
                conversation.id === activeId && "bg-muted font-medium",
              )}
              title={conversation.title ?? "Sin preguntas todavía"}
            >
              {conversation.title ?? <span className="text-muted-foreground italic">Sin preguntas</span>}
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
