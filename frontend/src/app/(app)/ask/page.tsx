"use client";

import { FileText, Loader2, MessageSquare, Square } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";

import { ErrorMessage } from "@/components/form";
import { PageHeader } from "@/components/people";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { errorMessage } from "@/lib/api/client";
import { askQuestion, splitCitations, type ChatEvent, type Citation } from "@/lib/chat";
import { pageRange } from "@/lib/documents";
import { useActiveOrganization } from "@/lib/organizations";

type Answer = {
  question: string;
  text: string;
  citations: Citation[];
  queuePosition: number | null;
  status: "waiting" | "writing" | "done" | "stopped" | "failed";
  noEvidence: boolean;
  error: string | null;
};

const EMPTY: Omit<Answer, "question"> = {
  text: "",
  citations: [],
  queuePosition: null,
  status: "waiting",
  noEvidence: false,
  error: null,
};

function apply(answer: Answer, event: ChatEvent): Answer {
  switch (event.event) {
    case "queued":
      return { ...answer, queuePosition: event.data.position };
    case "token":
      return { ...answer, status: "writing", queuePosition: null, text: answer.text + event.data.text };
    case "citations":
      return { ...answer, citations: event.data.citations };
    case "done":
      return { ...answer, status: "done", noEvidence: event.data.no_evidence };
    case "error":
      return { ...answer, status: "failed", error: event.data.message };
  }
}

export default function AskPage() {
  const { organization } = useActiveOrganization();
  const [draft, setDraft] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const controller = useRef<AbortController | null>(null);
  const busy = answer?.status === "waiting" || answer?.status === "writing";

  if (!organization) return null;
  const organizationId = organization.id;

  async function ask(question: string) {
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    setAnswer({ question, ...EMPTY });
    try {
      await askQuestion(
        organizationId,
        question,
        (event) => setAnswer((current) => (current ? apply(current, event) : current)),
        abort.signal,
      );
      // A stream that ends without "done" (connection cut) is not a finished answer.
      setAnswer((current) =>
        current && (current.status === "waiting" || current.status === "writing")
          ? { ...current, status: "failed", error: "Se cortó la conexión antes de terminar" }
          : current,
      );
    } catch (error) {
      if (abort.signal.aborted) {
        setAnswer((current) => (current ? { ...current, status: "stopped" } : current));
      } else {
        setAnswer((current) =>
          current ? { ...current, status: "failed", error: errorMessage(error) } : current,
        );
      }
    }
  }

  return (
    <>
      <PageHeader
        title="Preguntar"
        description="Hacé una pregunta y la IA responde solo con los documentos de tu organización, citando de dónde sale cada dato."
      />
      <form
        className="mb-8 flex flex-wrap gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          const question = draft.trim();
          if (question && !busy) void ask(question);
        }}
      >
        <label htmlFor="question" className="sr-only">
          Tu pregunta
        </label>
        <Input
          id="question"
          name="question"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Por ejemplo: ¿cuánto dura el período de prueba?"
          maxLength={1000}
          className="h-11 min-w-64 flex-1"
          autoFocus
        />
        {busy ? (
          <Button type="button" size="lg" variant="outline" onClick={() => controller.current?.abort()}>
            <Square />
            Detener
          </Button>
        ) : (
          <Button type="submit" size="lg" disabled={!draft.trim()}>
            <MessageSquare />
            Preguntar
          </Button>
        )}
      </form>

      {answer && <AnswerView answer={answer} />}
    </>
  );
}

function AnswerView({ answer }: { answer: Answer }) {
  const byMarker = new Map(answer.citations.map((c) => [c.marker, c]));
  return (
    <section aria-label="Respuesta" className="grid gap-6">
      <div className="rounded-2xl border bg-card p-5">
        <p className="mb-3 text-sm font-medium text-muted-foreground">{answer.question}</p>

        {answer.status === "waiting" && (
          <p className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
            <Loader2 className="size-4 animate-spin" />
            {answer.queuePosition
              ? `En espera: ${answer.queuePosition === 1 ? "sos la próxima pregunta" : `hay ${answer.queuePosition - 1} preguntas antes que la tuya`}.`
              : "Buscando en los documentos…"}
          </p>
        )}

        {answer.text && (
          <p
            className={
              answer.noEvidence
                ? "leading-relaxed whitespace-pre-line text-muted-foreground italic"
                : "leading-relaxed whitespace-pre-line"
            }
            aria-live="polite"
          >
            {splitCitations(answer.text).map((part, i) =>
              "marker" in part ? (
                <CitationMark key={i} marker={part.marker} citation={byMarker.get(part.marker)} />
              ) : (
                <span key={i}>{part.text}</span>
              ),
            )}
            {answer.status === "writing" && <span className="ml-0.5 animate-pulse">▍</span>}
          </p>
        )}

        {answer.status === "stopped" && (
          <p className="mt-3 text-sm text-muted-foreground">Detuviste la respuesta.</p>
        )}
        {answer.status === "failed" && <ErrorMessage message={answer.error} />}
      </div>

      {answer.citations.length > 0 && (
        <div>
          <h2 className="mb-3 text-sm font-semibold">Fuentes</h2>
          <ol className="grid gap-3">
            {answer.citations.map((citation) => (
              <li
                key={citation.marker}
                id={`fuente-${citation.marker}`}
                className="rounded-2xl border bg-card p-4 text-sm"
              >
                <div className="mb-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
                  <span className="rounded bg-primary/10 px-1.5 font-mono text-xs text-primary">
                    [{citation.marker}]
                  </span>
                  <Link
                    href={`/documents/${citation.document_id}`}
                    className="inline-flex items-center gap-1.5 font-medium text-primary hover:underline"
                  >
                    <FileText className="size-4" />
                    {citation.document_title}
                  </Link>
                  {pageRange(citation.page_start, citation.page_end) && (
                    <span className="text-muted-foreground">
                      {pageRange(citation.page_start, citation.page_end)}
                    </span>
                  )}
                </div>
                <p className="leading-relaxed text-muted-foreground">{citation.excerpt}</p>
              </li>
            ))}
          </ol>
        </div>
      )}

      <p className="text-xs text-muted-foreground">
        Las respuestas las genera un modelo de IA local y pueden tener errores: revisá las fuentes.
      </p>
    </section>
  );
}

function CitationMark({ marker, citation }: { marker: number; citation: Citation | undefined }) {
  // The citations arrive at the end: until then the marker is plain text.
  if (!citation) return <span className="font-mono text-xs text-muted-foreground">[{marker}]</span>;
  const pages = pageRange(citation.page_start, citation.page_end);
  return (
    <a
      href={`#fuente-${marker}`}
      title={`${citation.document_title}${pages ? `, ${pages}` : ""}`}
      className="mx-0.5 rounded bg-primary/10 px-1 align-baseline font-mono text-xs text-primary no-underline hover:bg-primary/20"
    >
      {marker}
    </a>
  );
}
