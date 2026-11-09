"use client";

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, Check, Loader2, RotateCcw } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { ErrorMessage } from "@/components/form";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, errorMessage, inOrganization, unwrap, type ProcessingRead } from "@/lib/api/client";
import { isProcessingFinal, pageRange, PROCESSING_STEPS } from "@/lib/documents";
import { cn } from "@/lib/utils";

const POLL_MS = 2000;

/** Which step the job is on, for the step list (failed shows where it stopped). */
function stepIndex(job: ProcessingRead): number {
  if (job.status === "failed") return -1;
  return PROCESSING_STEPS.findIndex((step) => step.status === job.status);
}

export function ProcessingPanel({
  organizationId,
  documentId,
  canReprocess,
  onFinished,
}: {
  organizationId: string;
  documentId: string;
  canReprocess: boolean;
  onFinished: () => unknown;
}) {
  const queryClient = useQueryClient();
  const key = ["processing", organizationId, documentId];
  const [reprocessError, setReprocessError] = useState<string | null>(null);

  const processing = useQuery({
    queryKey: key,
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/documents/{document_id}/processing", {
          params: { ...inOrganization(organizationId), path: { document_id: documentId } },
        }),
      ),
    // Ask again every 2 s while the worker is busy; stop once it is ready or failed.
    refetchInterval: (query) => (isProcessingFinal(query.state.data?.status) ? false : POLL_MS),
  });

  // When it finishes, the document (status) and its chunks changed: refresh them once.
  const previous = useRef<string | null | undefined>(undefined);
  const status = processing.data?.status;
  useEffect(() => {
    if (previous.current !== undefined && previous.current !== status && isProcessingFinal(status)) {
      void onFinished();
    }
    previous.current = status;
  }, [status, onFinished]);

  const reprocess = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST("/api/v1/documents/{document_id}/reprocess", {
          params: { ...inOrganization(organizationId), path: { document_id: documentId } },
        }),
      ),
    onMutate: () => setReprocessError(null),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: key }),
    onError: (error) => setReprocessError(errorMessage(error)),
  });

  const job = processing.data;
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>Procesamiento</CardTitle>
        {canReprocess && job && isProcessingFinal(job.status) && (
          <Button variant="outline" size="sm" disabled={reprocess.isPending} onClick={() => reprocess.mutate()}>
            <RotateCcw />
            Reprocesar
          </Button>
        )}
      </CardHeader>
      <CardContent className="grid gap-4 text-sm">
        <ErrorMessage message={processing.error ? errorMessage(processing.error) : reprocessError} />
        {job && job.status === null && (
          <p className="text-muted-foreground">
            Este documento se subió antes de que existiera el procesamiento.
            {canReprocess && " Tocá «Reprocesar» para procesarlo."}
          </p>
        )}
        {job && job.status !== null && (
          <>
            <ol className="grid gap-2" aria-label="Pasos del procesamiento">
              {PROCESSING_STEPS.filter((step) => step.status !== "ocr" || job.ocr_pages > 0 || job.status === "ocr").map(
                (step) => {
                  const current = stepIndex(job);
                  const index = PROCESSING_STEPS.findIndex((s) => s.status === step.status);
                  const done = job.status === "ready" || (current >= 0 && index < current);
                  const active = index === current && job.status !== "ready";
                  return (
                    <li key={step.status} className="flex items-center gap-2.5">
                      <span
                        className={cn(
                          "grid size-5 shrink-0 place-items-center rounded-full border",
                          done && "border-success bg-success text-white",
                          active && "border-primary text-primary",
                        )}
                      >
                        {done ? (
                          <Check className="size-3" />
                        ) : active ? (
                          <Loader2 className="size-3 animate-spin" />
                        ) : null}
                      </span>
                      <span className={cn(!done && !active && "text-muted-foreground", active && "font-medium")}>
                        {step.label}
                        {active && step.status === "extracting" && job.pages_total
                          ? ` (${job.pages_done} de ${job.pages_total} páginas)`
                          : ""}
                      </span>
                    </li>
                  );
                },
              )}
            </ol>
            {job.status === "failed" && (
              <p className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-destructive">
                <AlertCircle className="mt-0.5 size-4 shrink-0" />
                {job.error ?? "No se pudo procesar el documento."}
              </p>
            )}
            {job.status === "ready" && (
              <p className="text-muted-foreground">
                {job.pages_total ?? 0} {job.pages_total === 1 ? "página" : "páginas"}
                {job.ocr_pages > 0 && ` (${job.ocr_pages} con OCR)`} · {job.chunk_count}{" "}
                {job.chunk_count === 1 ? "fragmento" : "fragmentos"}
              </p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

export function ChunkList({ organizationId, documentId }: { organizationId: string; documentId: string }) {
  const chunks = useInfiniteQuery({
    queryKey: ["chunks", organizationId, documentId],
    initialPageParam: null as number | null,
    queryFn: async ({ pageParam }) =>
      unwrap(
        await api.GET("/api/v1/documents/{document_id}/chunks", {
          params: {
            ...inOrganization(organizationId),
            path: { document_id: documentId },
            query: { limit: 20, cursor: pageParam },
          },
        }),
      ),
    getNextPageParam: (last) => (last.next_cursor ? Number(last.next_cursor) : null),
  });
  const items = chunks.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <Card className="gap-0 overflow-hidden">
      <CardHeader className="pb-4">
        <CardTitle>Fragmentos</CardTitle>
        <p className="text-sm text-muted-foreground">
          Las piezas en que se dividió el documento. Las respuestas del chat van a citar estas piezas.
        </p>
      </CardHeader>
      <CardContent className="grid gap-3">
        <ErrorMessage message={chunks.error ? errorMessage(chunks.error) : null} />
        {chunks.isSuccess && items.length === 0 && (
          <p className="text-sm text-muted-foreground">Todavía no hay fragmentos.</p>
        )}
        {items.map((chunk) => (
          <article key={chunk.position} className="rounded-xl border bg-muted/30 p-4">
            <header className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
              <span className="rounded-md bg-card px-1.5 py-0.5 font-mono">#{chunk.position + 1}</span>
              {chunk.section && <span className="font-medium text-foreground">{chunk.section}</span>}
              {pageRange(chunk.page_start, chunk.page_end) && <span>{pageRange(chunk.page_start, chunk.page_end)}</span>}
              <span className="ml-auto">{chunk.token_count} tokens aprox.</span>
            </header>
            <p className="text-sm leading-relaxed whitespace-pre-line">{chunk.content}</p>
          </article>
        ))}
        {chunks.hasNextPage && (
          <Button
            variant="outline"
            className="w-fit justify-self-center"
            disabled={chunks.isFetchingNextPage}
            onClick={() => void chunks.fetchNextPage()}
          >
            {chunks.isFetchingNextPage ? "Cargando…" : "Ver más fragmentos"}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
