"use client";

import { useQuery } from "@tanstack/react-query";
import { FileText, Search as SearchIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { ErrorMessage } from "@/components/form";
import { PageHeader } from "@/components/people";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { api, errorMessage, inOrganization, unwrap, type SearchMode } from "@/lib/api/client";
import { pageRange } from "@/lib/documents";
import { useActiveOrganization } from "@/lib/organizations";
import { highlightTerms } from "@/lib/search";

const MODES: { value: SearchMode; label: string }[] = [
  { value: "hybrid", label: "Híbrida (recomendada)" },
  { value: "vector", label: "Por significado" },
  { value: "text", label: "Por palabras" },
];

export default function SearchPage() {
  const { organization } = useActiveOrganization();
  const organizationId = organization?.id ?? "";
  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<SearchMode>("hybrid");

  const results = useQuery({
    queryKey: ["search", organizationId, query, mode],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/search", {
          params: { ...inOrganization(organizationId), query: { q: query, mode, limit: 10 } },
        }),
      ),
    enabled: Boolean(organization) && query.length > 0,
  });

  if (!organization) return null;

  return (
    <>
      <PageHeader
        title="Búsqueda"
        description="Escribí una pregunta o unas palabras: busca en todos los documentos procesados de tu organización."
      />
      <form
        className="mb-8 flex flex-wrap gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          setQuery(draft.trim());
        }}
      >
        <label htmlFor="q" className="sr-only">
          Qué buscar
        </label>
        <Input
          id="q"
          name="q"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Por ejemplo: ¿cuántos días de vacaciones me corresponden?"
          maxLength={500}
          className="h-11 min-w-64 flex-1"
          autoFocus
        />
        <label htmlFor="mode" className="sr-only">
          Modo de búsqueda
        </label>
        <NativeSelect
          id="mode"
          className="h-11"
          value={mode}
          onChange={(event) => setMode(event.target.value as SearchMode)}
        >
          {MODES.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </NativeSelect>
        <Button type="submit" size="lg" disabled={!draft.trim()}>
          <SearchIcon />
          Buscar
        </Button>
      </form>

      <ErrorMessage message={results.error ? errorMessage(results.error) : null} />
      {results.isFetching && <p className="text-sm text-muted-foreground">Buscando…</p>}
      {results.data?.notes.map((note) => (
        <p key={note} className="mb-4 text-sm text-muted-foreground">
          {note}
        </p>
      ))}
      {results.isSuccess && !results.isFetching && results.data.items.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No se encontró nada. Probá con otras palabras, o revisá que los documentos estén «Listos».
        </p>
      )}

      <ol className="grid gap-4" aria-label="Resultados">
        {results.data?.items.map((hit, index) => (
          <li key={hit.chunk_id} className="rounded-2xl border bg-card p-5">
            <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
              <span className="font-mono text-xs text-muted-foreground">#{index + 1}</span>
              <Link
                href={`/documents/${hit.document_id}`}
                className="inline-flex items-center gap-1.5 font-medium text-primary hover:underline"
              >
                <FileText className="size-4" />
                {hit.document_title}
              </Link>
              {pageRange(hit.page_start, hit.page_end) && (
                <span className="text-muted-foreground">{pageRange(hit.page_start, hit.page_end)}</span>
              )}
              <span className="ml-auto text-xs text-muted-foreground" title="Posición en cada ranking">
                {hit.vector_rank != null && `significado #${hit.vector_rank}`}
                {hit.vector_rank != null && hit.text_rank != null && " · "}
                {hit.text_rank != null && `palabras #${hit.text_rank}`}
              </span>
            </div>
            {hit.section && <p className="mb-1.5 text-sm font-medium">{hit.section}</p>}
            <p className="line-clamp-[10] text-sm leading-relaxed whitespace-pre-line text-muted-foreground">
              {highlightTerms(hit.content, query).map((part, i) =>
                part.match ? (
                  <mark key={i} className="rounded bg-warning/25 px-0.5 text-foreground">
                    {part.text}
                  </mark>
                ) : (
                  <span key={i}>{part.text}</span>
                ),
              )}
            </p>
          </li>
        ))}
      </ol>
    </>
  );
}
