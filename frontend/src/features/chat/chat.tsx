"use client";

/**
 * A conversation: its history, the answer being written, and the question box (stage 8).
 *
 * Saved messages come from GET /conversations/{id}. While a question is being answered, the
 * live answer is drawn from the SSE events; when it ends, the conversation is fetched again
 * (now with the saved answer) and the live copy is dropped.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, MessageSquare, Square, ThumbsDown, ThumbsUp, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { ErrorMessage } from "@/components/form";
import { Button } from "@/components/ui/button";
import { api, errorMessage, inOrganization, unwrap, type Schemas } from "@/lib/api/client";
import { askQuestion, type ChatEvent, type Citation } from "@/lib/chat";
import { pageRange } from "@/lib/documents";
import { cn } from "@/lib/utils";

import { AnswerMarkdown } from "./answer-markdown";
import { conversationsKey } from "./conversation-list";
import { ScopePicker, scopeLabel, useReadyDocuments } from "./scope-picker";
import { SourcePanel } from "./source-panel";

type MessageRead = Schemas["MessageRead"];

type Live = {
  question: string;
  text: string;
  citations: Citation[];
  queuePosition: number | null;
  status: "waiting" | "writing" | "done" | "stopped" | "failed";
  noEvidence: boolean;
  error: string | null;
};

const EMPTY_LIVE: Omit<Live, "question"> = {
  text: "",
  citations: [],
  queuePosition: null,
  status: "waiting",
  noEvidence: false,
  error: null,
};

export function applyEvent(live: Live, event: ChatEvent): Live {
  switch (event.event) {
    case "message":
      return live;
    case "queued":
      return { ...live, queuePosition: event.data.position };
    case "token":
      return { ...live, status: "writing", queuePosition: null, text: live.text + event.data.text };
    case "citations":
      return { ...live, citations: event.data.citations };
    case "done":
      return { ...live, status: "done", noEvidence: event.data.no_evidence };
    case "error":
      return { ...live, status: "failed", error: event.data.message };
  }
}

function conversationKey(organizationId: string, conversationId: string | null) {
  return ["conversation", organizationId, conversationId];
}

export function Chat({ organizationId, conversationId }: { organizationId: string; conversationId: string | null }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState("");
  const [scope, setScope] = useState<string[] | null>(null);
  const [live, setLive] = useState<Live | null>(null);
  const [source, setSource] = useState<Citation | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  const busy = live?.status === "waiting" || live?.status === "writing";

  const detail = useQuery({
    queryKey: conversationKey(organizationId, conversationId),
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/conversations/{conversation_id}", {
          params: { ...inOrganization(organizationId), path: { conversation_id: conversationId ?? "" } },
        }),
      ),
    enabled: Boolean(conversationId),
  });
  const documents = useReadyDocuments(organizationId);
  const titles = new Map((documents.data ?? []).map((doc) => [doc.id, doc.title]));

  const remove = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.DELETE("/api/v1/conversations/{conversation_id}", {
          params: { ...inOrganization(organizationId), path: { conversation_id: conversationId ?? "" } },
        }),
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: conversationsKey(organizationId) });
      router.replace("/ask");
    },
  });

  async function ask(question: string) {
    setFailure(null);
    let id = conversationId;
    if (!id) {
      try {
        const created = unwrap(
          await api.POST("/api/v1/conversations", {
            params: inOrganization(organizationId),
            body: { document_ids: scope && scope.length > 0 ? scope : null },
          }),
        );
        id = created.id;
        router.replace(`/ask?c=${id}`);
      } catch (error) {
        setFailure(errorMessage(error));
        return;
      }
    }
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    setDraft("");
    setLive({ question, ...EMPTY_LIVE });
    try {
      await askQuestion(
        organizationId,
        question,
        (event) => setLive((current) => (current ? applyEvent(current, event) : current)),
        abort.signal,
        id,
      );
      setLive((current) =>
        current && (current.status === "waiting" || current.status === "writing")
          ? { ...current, status: "failed", error: "Se cortó la conexión antes de terminar" }
          : current,
      );
    } catch (error) {
      setLive((current) =>
        current
          ? abort.signal.aborted
            ? { ...current, status: "stopped" }
            : { ...current, status: "failed", error: errorMessage(error) }
          : current,
      );
    }
    // The answer is saved (also when stopped or failed): show the saved copy.
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: conversationKey(organizationId, id) }),
      queryClient.invalidateQueries({ queryKey: conversationsKey(organizationId) }),
    ]);
    setLive((current) => (current && current.status !== "failed" ? null : current));
  }

  const messages = conversationId ? (detail.data?.messages ?? []) : [];
  const turns = pairUp(messages);

  return (
    <div className="grid min-w-0 gap-6">
      {conversationId && detail.data && (
        <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
          <p className="text-muted-foreground">{scopeLabel(detail.data.document_ids, titles)}</p>
          <Button
            variant="ghost"
            size="sm"
            className="text-muted-foreground"
            onClick={() => remove.mutate()}
            disabled={remove.isPending || busy}
          >
            <Trash2 />
            Borrar conversación
          </Button>
        </div>
      )}
      <ErrorMessage message={detail.error ? errorMessage(detail.error) : remove.error ? errorMessage(remove.error) : null} />

      {!conversationId && !live && (
        <div className="rounded-2xl border bg-card p-5">
          <ScopePicker organizationId={organizationId} selected={scope} onChange={setScope} />
        </div>
      )}

      {turns.map(({ question, answer }) => (
        <Turn
          key={question.id}
          question={question.content}
          answer={answer}
          organizationId={organizationId}
          conversationId={conversationId ?? ""}
          onOpenSource={setSource}
        />
      ))}

      {live && <LiveAnswer live={live} onOpenSource={setSource} />}

      <form
        className="sticky bottom-4 flex flex-wrap gap-3 rounded-2xl border bg-background/95 p-3 shadow-sm backdrop-blur"
        onSubmit={(event) => {
          event.preventDefault();
          const question = draft.trim();
          if (question && !busy) void ask(question);
        }}
      >
        <label htmlFor="question" className="sr-only">
          Tu pregunta
        </label>
        <textarea
          id="question"
          name="question"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              event.currentTarget.form?.requestSubmit();
            }
          }}
          placeholder={
            turns.length > 0
              ? "Seguí preguntando: «¿y en ese caso?»"
              : "Por ejemplo: ¿cuánto dura el período de prueba?"
          }
          maxLength={1000}
          rows={1}
          className="min-h-11 min-w-0 flex-1 resize-none rounded-lg border bg-background px-3 py-2.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
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
      <ErrorMessage message={failure} />
      <p className="text-xs text-muted-foreground">
        Las respuestas las genera un modelo de IA local y pueden tener errores: revisá las fuentes.
      </p>

      {source && (
        <SourcePanel organizationId={organizationId} citation={source} onClose={() => setSource(null)} />
      )}
    </div>
  );
}

type TurnData = { question: MessageRead; answer: MessageRead | null };

export function pairUp(messages: MessageRead[]): TurnData[] {
  const turns: TurnData[] = [];
  for (const message of messages) {
    const last = turns.at(-1);
    if (message.role === "user") turns.push({ question: message, answer: null });
    else if (last) last.answer = message;
  }
  return turns;
}

const STATUS_NOTES: Record<string, string> = {
  stopped: "Detuviste la respuesta.",
  failed: "No se pudo terminar la respuesta.",
  streaming: "La respuesta se interrumpió.",
};

function Turn({
  question,
  answer,
  organizationId,
  conversationId,
  onOpenSource,
}: {
  question: string;
  answer: MessageRead | null;
  organizationId: string;
  conversationId: string;
  onOpenSource: (citation: Citation) => void;
}) {
  return (
    <section className="grid gap-3">
      <Question text={question} />
      {answer && (
        <div className="rounded-2xl border bg-card p-5">
          <AnswerText
            text={answer.content}
            citations={answer.citations}
            noEvidence={Boolean(answer.no_evidence)}
            onOpenSource={onOpenSource}
          />
          {STATUS_NOTES[answer.status] && (
            <p className="mt-3 text-sm text-muted-foreground">{STATUS_NOTES[answer.status]}</p>
          )}
          <Sources citations={answer.citations} onOpenSource={onOpenSource} />
          {answer.status === "complete" && (
            <Feedback organizationId={organizationId} conversationId={conversationId} answer={answer} />
          )}
        </div>
      )}
    </section>
  );
}

function Question({ text }: { text: string }) {
  return (
    <p className="ml-auto max-w-[85%] rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 text-sm text-primary-foreground">
      {text}
    </p>
  );
}

function LiveAnswer({ live, onOpenSource }: { live: Live; onOpenSource: (citation: Citation) => void }) {
  return (
    <section className="grid gap-3" aria-label="Respuesta en curso">
      <Question text={live.question} />
      <div className="rounded-2xl border bg-card p-5">
        {live.status === "waiting" && (
          <p className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
            <Loader2 className="size-4 animate-spin" />
            {live.queuePosition
              ? `En espera: ${live.queuePosition === 1 ? "sos la próxima pregunta" : `hay ${live.queuePosition - 1} preguntas antes que la tuya`}.`
              : "Buscando en los documentos…"}
          </p>
        )}
        {live.text && (
          <AnswerText
            text={live.text}
            citations={live.citations}
            noEvidence={live.noEvidence}
            writing={live.status === "writing"}
            onOpenSource={onOpenSource}
          />
        )}
        {live.status === "stopped" && <p className="mt-3 text-sm text-muted-foreground">Detuviste la respuesta.</p>}
        {live.status === "failed" && <ErrorMessage message={live.error} />}
        <Sources citations={live.citations} onOpenSource={onOpenSource} />
      </div>
    </section>
  );
}

function AnswerText({
  text,
  citations,
  noEvidence,
  writing = false,
  onOpenSource,
}: {
  text: string;
  citations: Citation[];
  noEvidence: boolean;
  writing?: boolean;
  onOpenSource: (citation: Citation) => void;
}) {
  const byMarker = new Map(citations.map((c) => [c.marker, c]));
  return (
    <div className={cn(noEvidence && "text-muted-foreground italic")} aria-live={writing ? "polite" : undefined}>
      <AnswerMarkdown
        text={text}
        renderCitation={(marker, key) => (
          <CitationMark key={key} marker={marker} citation={byMarker.get(marker)} onOpen={onOpenSource} />
        )}
        cursor={writing ? <span className="ml-0.5 animate-pulse">▍</span> : undefined}
      />
    </div>
  );
}

function CitationMark({
  marker,
  citation,
  onOpen,
}: {
  marker: number;
  citation: Citation | undefined;
  onOpen: (citation: Citation) => void;
}) {
  // The citations arrive at the end: until then the marker is plain text.
  if (!citation) return <span className="font-mono text-xs text-muted-foreground">[{marker}]</span>;
  const pages = pageRange(citation.page_start, citation.page_end);
  return (
    <button
      type="button"
      onClick={() => onOpen(citation)}
      title={`${citation.document_title}${pages ? `, ${pages}` : ""}`}
      className="mx-0.5 rounded bg-primary/10 px-1 align-baseline font-mono text-xs text-primary hover:bg-primary/20"
    >
      {marker}
    </button>
  );
}

function Sources({ citations, onOpenSource }: { citations: Citation[]; onOpenSource: (citation: Citation) => void }) {
  if (citations.length === 0) return null;
  return (
    <ol className="mt-4 grid gap-2 border-t pt-4" aria-label="Fuentes">
      {citations.map((citation) => (
        <li key={citation.marker}>
          <button
            type="button"
            onClick={() => onOpenSource(citation)}
            className="flex w-full items-start gap-2 rounded-lg p-2 text-left text-sm hover:bg-muted"
          >
            <span className="rounded bg-primary/10 px-1.5 font-mono text-xs text-primary">[{citation.marker}]</span>
            <span className="min-w-0 flex-1">
              <span className="font-medium">{citation.document_title}</span>
              {pageRange(citation.page_start, citation.page_end) && (
                <span className="text-muted-foreground"> · {pageRange(citation.page_start, citation.page_end)}</span>
              )}
              <span className="mt-0.5 line-clamp-2 block text-muted-foreground">{citation.excerpt}</span>
            </span>
          </button>
        </li>
      ))}
    </ol>
  );
}

function Feedback({
  organizationId,
  conversationId,
  answer,
}: {
  organizationId: string;
  conversationId: string;
  answer: MessageRead;
}) {
  const queryClient = useQueryClient();
  const rate = useMutation({
    mutationFn: async (feedback: "helpful" | "not_helpful" | null) =>
      unwrap(
        await api.PUT("/api/v1/conversations/{conversation_id}/messages/{message_id}/feedback", {
          params: {
            ...inOrganization(organizationId),
            path: { conversation_id: conversationId, message_id: answer.id },
          },
          body: { feedback },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: conversationKey(organizationId, conversationId) }),
  });
  const current = rate.isPending ? rate.variables : answer.feedback;

  return (
    <div className="mt-4 flex items-center gap-1 text-xs text-muted-foreground">
      <span className="mr-1">¿Te sirvió?</span>
      <Button
        variant={current === "helpful" ? "secondary" : "ghost"}
        size="sm"
        aria-pressed={current === "helpful"}
        aria-label="Útil"
        onClick={() => rate.mutate(current === "helpful" ? null : "helpful")}
      >
        <ThumbsUp />
      </Button>
      <Button
        variant={current === "not_helpful" ? "secondary" : "ghost"}
        size="sm"
        aria-pressed={current === "not_helpful"}
        aria-label="No útil"
        onClick={() => rate.mutate(current === "not_helpful" ? null : "not_helpful")}
      >
        <ThumbsDown />
      </Button>
      {current === "not_helpful" && <span>Gracias: la usamos para mejorar las respuestas.</span>}
      {rate.error && <span className="text-destructive">{errorMessage(rate.error)}</span>}
    </div>
  );
}
