"use client";

/** Which documents a new conversation asks about: all of them, or a selection (stage 8). */

import { useQuery } from "@tanstack/react-query";
import { FileText } from "lucide-react";

import { api, inOrganization, unwrap } from "@/lib/api/client";

export const MAX_SCOPE = 50;

export function useReadyDocuments(organizationId: string) {
  return useQuery({
    queryKey: ["documents", organizationId, "scope"],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/documents", {
          params: { ...inOrganization(organizationId), query: { limit: 100 } },
        }),
      ).items,
  });
}

export function ScopePicker({
  organizationId,
  selected,
  onChange,
}: {
  organizationId: string;
  selected: string[] | null; // null: all documents
  onChange: (selected: string[] | null) => void;
}) {
  const documents = useReadyDocuments(organizationId);
  const items = documents.data ?? [];
  const chosen = new Set(selected ?? []);

  return (
    <fieldset className="grid gap-2 text-sm">
      <legend className="mb-1 font-medium">¿Sobre qué documentos?</legend>
      <label className="flex items-center gap-2">
        <input
          type="radio"
          name="scope"
          checked={selected === null}
          onChange={() => onChange(null)}
        />
        Todos los documentos de la organización
      </label>
      <label className="flex items-center gap-2">
        <input
          type="radio"
          name="scope"
          checked={selected !== null}
          onChange={() => onChange([])}
          disabled={items.length === 0}
        />
        Solo algunos
      </label>
      {selected !== null && (
        <ul className="ml-6 grid max-h-56 gap-1 overflow-y-auto rounded-lg border p-2">
          {items.map((doc) => (
            <li key={doc.id}>
              <label className="flex items-center gap-2 rounded px-1 py-0.5 hover:bg-muted">
                <input
                  type="checkbox"
                  checked={chosen.has(doc.id)}
                  disabled={!chosen.has(doc.id) && chosen.size >= MAX_SCOPE}
                  onChange={(event) =>
                    onChange(
                      event.target.checked
                        ? [...chosen, doc.id]
                        : [...chosen].filter((id) => id !== doc.id),
                    )
                  }
                />
                <FileText className="size-3.5 shrink-0 text-muted-foreground" />
                <span className="truncate">{doc.title}</span>
                {doc.status !== "ready" && (
                  <span className="ml-auto text-xs text-muted-foreground">sin procesar</span>
                )}
              </label>
            </li>
          ))}
        </ul>
      )}
    </fieldset>
  );
}

/** "Todos los documentos" / "3 documentos: Contrato, Ley…" for the header of a conversation. */
export function scopeLabel(documentIds: string[] | null | undefined, titles: Map<string, string>): string {
  if (!documentIds || documentIds.length === 0) return "Todos los documentos";
  const names = documentIds.map((id) => titles.get(id) ?? "documento eliminado");
  const shown = names.slice(0, 2).join(", ");
  const rest = names.length > 2 ? ` y ${names.length - 2} más` : "";
  return `${documentIds.length === 1 ? "1 documento" : `${documentIds.length} documentos`}: ${shown}${rest}`;
}
