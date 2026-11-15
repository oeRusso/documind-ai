"use client";

/**
 * The source of a citation, next to the chat: document, pages, the excerpt and, for PDFs, the
 * cited page with the text highlighted (stage 8, "clic en la cita → ver la página").
 */

import { useQuery } from "@tanstack/react-query";
import { ExternalLink, FileText, X } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect } from "react";

import { Button } from "@/components/ui/button";
import { api, inOrganization, unwrap } from "@/lib/api/client";
import type { Citation } from "@/lib/chat";
import { pageRange } from "@/lib/documents";

// pdf.js only runs in the browser, and only when a source is opened.
const PdfPage = dynamic(() => import("./pdf-page").then((m) => m.PdfPage), { ssr: false });

export function SourcePanel({
  organizationId,
  citation,
  onClose,
}: {
  organizationId: string;
  citation: Citation;
  onClose: () => void;
}) {
  const documentId = citation.document_id;
  const detail = useQuery({
    queryKey: ["document", organizationId, documentId],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/documents/{document_id}", {
          params: { ...inOrganization(organizationId), path: { document_id: documentId ?? "" } },
        }),
      ),
    enabled: Boolean(documentId),
    retry: false,
  });

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const pages = pageRange(citation.page_start, citation.page_end);
  const isPdf = detail.data?.versions[0]?.kind === "pdf";
  const gone = !documentId || detail.isError;

  return (
    <aside
      aria-label="Fuente citada"
      className="fixed inset-y-0 right-0 z-30 flex w-full max-w-2xl flex-col border-l bg-background shadow-2xl"
    >
      <header className="flex items-start gap-3 border-b p-4">
        <span className="mt-0.5 rounded bg-primary/10 px-1.5 font-mono text-xs text-primary">
          [{citation.marker}]
        </span>
        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-1.5 font-medium">
            <FileText className="size-4 shrink-0" />
            <span className="truncate">{citation.document_title}</span>
          </p>
          {pages && <p className="text-sm text-muted-foreground">{pages}</p>}
        </div>
        {documentId && !gone && (
          <Button asChild variant="ghost" size="sm">
            <Link href={`/documents/${documentId}`}>
              <ExternalLink />
              Documento
            </Link>
          </Button>
        )}
        <Button variant="ghost" size="sm" onClick={onClose} aria-label="Cerrar">
          <X />
        </Button>
      </header>
      <div className="grid flex-1 content-start gap-4 overflow-y-auto p-4">
        <figure className="rounded-xl border-l-4 border-yellow-400 bg-yellow-50 p-3 text-sm leading-relaxed dark:bg-yellow-950/30">
          <figcaption className="mb-1 text-xs font-medium text-muted-foreground">Fragmento citado</figcaption>
          <mark className="bg-transparent text-foreground">{citation.excerpt}</mark>
        </figure>
        {gone && (
          <p className="text-sm text-muted-foreground">
            El documento ya no está disponible: se conserva el fragmento que se citó.
          </p>
        )}
        {documentId && isPdf && citation.page_start && (
          <PdfPage
            organizationId={organizationId}
            documentId={documentId}
            page={citation.page_start}
            excerpt={citation.excerpt}
          />
        )}
        {detail.data && !isPdf && (
          <p className="text-sm text-muted-foreground">
            Este documento no es un PDF: la vista de páginas solo existe para PDF.
          </p>
        )}
      </div>
    </aside>
  );
}
