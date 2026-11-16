"use client";

/**
 * One page of a PDF, drawn with pdf.js, with the cited text highlighted (stage 8).
 *
 * The file comes through the API with the session (the same download as the documents page),
 * so it never leaves the organization. pdf.js is loaded only when a citation is opened: it is
 * big, and most pages of the app do not need it. Its worker (the part that parses the PDF in
 * the background) is a file of the same package, served by Next.js: nothing external.
 */

import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Loader2 } from "lucide-react";
import "pdfjs-dist/web/pdf_viewer.css";
import { useEffect, useRef, useState } from "react";

import { ErrorMessage } from "@/components/form";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/api/client";
import { fetchDocumentFile } from "@/lib/documents";
import { excerptMatcher } from "@/lib/highlight";

type PdfJs = typeof import("pdfjs-dist");
type PdfDocument = Awaited<ReturnType<PdfJs["getDocument"]>["promise"]>;

let pdfjs: Promise<PdfJs> | null = null;

function loadPdfJs(): Promise<PdfJs> {
  pdfjs ??= import("pdfjs-dist").then((lib) => {
    lib.GlobalWorkerOptions.workerSrc = new URL(
      "pdfjs-dist/build/pdf.worker.min.mjs",
      import.meta.url,
    ).toString();
    return lib;
  });
  return pdfjs;
}

export function PdfPage({
  organizationId,
  documentId,
  page,
  excerpt,
}: {
  organizationId: string;
  documentId: string;
  page: number;
  excerpt: string;
}) {
  const [current, setCurrent] = useState(page);
  const [shownFor, setShownFor] = useState(page);
  if (shownFor !== page) {
    // Another citation of the same document: jump to its page.
    setShownFor(page);
    setCurrent(page);
  }

  const pdf = useQuery({
    queryKey: ["pdf", organizationId, documentId],
    queryFn: async () => {
      const [lib, blob] = await Promise.all([
        loadPdfJs(),
        fetchDocumentFile(organizationId, documentId),
      ]);
      return lib.getDocument({ data: new Uint8Array(await blob.arrayBuffer()) }).promise;
    },
    staleTime: Infinity,
    gcTime: 5 * 60_000,
  });

  const total = pdf.data?.numPages ?? 0;
  return (
    <div className="grid gap-3">
      <div className="flex items-center justify-between gap-2 text-sm">
        <Button
          variant="outline"
          size="sm"
          disabled={current <= 1}
          onClick={() => setCurrent((n) => n - 1)}
          aria-label="Página anterior"
        >
          <ChevronLeft />
        </Button>
        <span className="text-muted-foreground">
          Página {current}
          {total ? ` de ${total}` : ""}
          {current === page ? " · citada" : ""}
        </span>
        <Button
          variant="outline"
          size="sm"
          disabled={!total || current >= total}
          onClick={() => setCurrent((n) => n + 1)}
          aria-label="Página siguiente"
        >
          <ChevronRight />
        </Button>
      </div>
      {pdf.isPending && (
        <p className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
          <Loader2 className="size-4 animate-spin" />
          Abriendo el documento…
        </p>
      )}
      <ErrorMessage message={pdf.error ? errorMessage(pdf.error) : null} />
      {pdf.data && (
        <RenderedPage
          pdf={pdf.data}
          number={Math.min(Math.max(current, 1), pdf.data.numPages)}
          excerpt={current === page ? excerpt : ""}
        />
      )}
    </div>
  );
}

function RenderedPage({ pdf, number, excerpt }: { pdf: PdfDocument; number: number; excerpt: string }) {
  const box = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const textLayer = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const cleanups: (() => void)[] = [];
    (async () => {
      const lib = await loadPdfJs();
      const pdfPage = await pdf.getPage(number);
      if (cancelled || !box.current || !canvas.current || !textLayer.current) return;
      const width = box.current.clientWidth || 600;
      const viewport = pdfPage.getViewport({ scale: width / pdfPage.getViewport({ scale: 1 }).width });
      const ratio = window.devicePixelRatio || 1;
      canvas.current.width = Math.floor(viewport.width * ratio);
      canvas.current.height = Math.floor(viewport.height * ratio);
      canvas.current.style.width = `${viewport.width}px`;
      canvas.current.style.height = `${viewport.height}px`;
      const render = pdfPage.render({
        canvas: canvas.current,
        viewport,
        transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0],
      });
      cleanups.push(() => render.cancel());
      await render.promise;

      const layer = textLayer.current;
      layer.replaceChildren();
      const text = new lib.TextLayer({
        textContentSource: pdfPage.streamTextContent(),
        container: layer,
        viewport,
      });
      cleanups.push(() => text.cancel());
      await text.render();
      if (cancelled || !excerpt) return;
      const matches = excerptMatcher(excerpt);
      let first: HTMLElement | null = null;
      for (const span of layer.querySelectorAll<HTMLElement>("span")) {
        if (span.textContent && matches(span.textContent)) {
          span.classList.add("cited-text");
          first ??= span;
        }
      }
      first?.scrollIntoView({ block: "center", behavior: "smooth" });
    })().catch((error: unknown) => {
      if (!cancelled && (error as { name?: string })?.name !== "RenderingCancelledException") {
        setFailed("No se pudo mostrar la página");
      }
    });
    return () => {
      cancelled = true;
      cleanups.forEach((cleanup) => cleanup());
    };
  }, [pdf, number, excerpt]);

  return (
    <div ref={box} className="relative w-full overflow-hidden rounded-lg border bg-white">
      <ErrorMessage message={failed} />
      <canvas ref={canvas} aria-label={`Página ${number} del documento`} />
      <div ref={textLayer} className="textLayer" />
    </div>
  );
}
