import { describe, expect, it } from "vitest";

import type { Schemas } from "@/lib/api/client";
import { SseParser } from "@/lib/chat";

import { applyEvent, pairUp } from "./chat";
import { scopeLabel } from "./scope-picker";

const LIVE = {
  question: "¿Preaviso?",
  text: "",
  citations: [],
  queuePosition: null,
  status: "waiting" as const,
  noEvidence: false,
  error: null,
};

function message(id: string, role: "user" | "assistant", content: string): Schemas["MessageRead"] {
  return {
    id,
    role,
    content,
    status: "complete",
    no_evidence: null,
    feedback: null,
    citations: [],
    created_at: "2026-11-15T00:00:00Z",
  };
}

describe("the live answer", () => {
  it("ignores the message event and writes the tokens", () => {
    let live = applyEvent(LIVE, {
      event: "message",
      data: { conversation_id: "c", question_id: "q", answer_id: "a" },
    });
    live = applyEvent(live, { event: "token", data: { text: "Un mes" } });
    live = applyEvent(live, { event: "done", data: { no_evidence: false } });
    expect(live).toMatchObject({ text: "Un mes", status: "done" });
  });

  it("parses the message event of a conversation", () => {
    const [event] = new SseParser().push(
      'event: message\ndata: {"conversation_id":"c","question_id":"q","answer_id":"a"}\n\n',
    );
    expect(event).toEqual({
      event: "message",
      data: { conversation_id: "c", question_id: "q", answer_id: "a" },
    });
  });

  it("ignores a block without event name", () => {
    expect(new SseParser().push('data: {"x":1}\n\n')).toEqual([]);
  });
});

describe("pairUp", () => {
  it("puts each answer under its question, also an unanswered last one", () => {
    const turns = pairUp([
      message("1", "user", "¿A?"),
      message("2", "assistant", "A."),
      message("3", "user", "¿B?"),
    ]);
    expect(turns.map((t) => [t.question.content, t.answer?.content ?? null])).toEqual([
      ["¿A?", "A."],
      ["¿B?", null],
    ]);
  });
});

describe("scopeLabel", () => {
  const titles = new Map([
    ["a", "Contrato"],
    ["b", "Ley"],
    ["c", "Anexo"],
  ]);

  it("says all documents when there is no selection", () => {
    expect(scopeLabel(null, titles)).toBe("Todos los documentos");
    expect(scopeLabel([], titles)).toBe("Todos los documentos");
  });

  it("names the first two and counts the rest", () => {
    expect(scopeLabel(["a"], titles)).toBe("1 documento: Contrato");
    expect(scopeLabel(["a", "b", "c"], titles)).toBe("3 documentos: Contrato, Ley y 1 más");
  });

  it("marks documents that no longer exist", () => {
    expect(scopeLabel(["x"], titles)).toBe("1 documento: documento eliminado");
  });
});
