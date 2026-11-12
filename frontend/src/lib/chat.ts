/**
 * Ask a question and read the answer as it is written (POST /api/v1/chat, Server-Sent Events).
 *
 * The browser's EventSource only does GET and cannot send the Authorization header, so the
 * stream is read by hand: fetch, then the response body piece by piece. Each SSE event is a
 * block of `event: name` and `data: {json}` lines, separated by a blank line. Lines that start
 * with ":" are keep-alive comments (the API sends them while the question waits in line).
 */

import { createAuthFetch } from "@/lib/api/auth-fetch";
import { apiError, type ApiError } from "@/lib/api/client";
import { session } from "@/lib/api/session";

export type Citation = {
  marker: number;
  document_id: string;
  document_title: string;
  page_start: number | null;
  page_end: number | null;
  excerpt: string;
};

export type ChatEvent =
  | { event: "queued"; data: { position: number } }
  | { event: "token"; data: { text: string } }
  | { event: "citations"; data: { citations: Citation[] } }
  | { event: "done"; data: { no_evidence: boolean } }
  | { event: "error"; data: { code: string; message: string; request_id?: string } };

const KNOWN = new Set(["queued", "token", "citations", "done", "error"]);

/** Turns pieces of an SSE stream (cut anywhere) into whole events. */
export class SseParser {
  private buffer = "";

  push(chunk: string): ChatEvent[] {
    this.buffer += chunk.replace(/\r\n?/g, "\n");
    const events: ChatEvent[] = [];
    let end = this.buffer.indexOf("\n\n");
    while (end !== -1) {
      const block = this.buffer.slice(0, end);
      this.buffer = this.buffer.slice(end + 2);
      const event = parseBlock(block);
      if (event) events.push(event);
      end = this.buffer.indexOf("\n\n");
    }
    return events;
  }
}

function parseBlock(block: string): ChatEvent | null {
  let name = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line === "" || line.startsWith(":")) continue; // keep-alive comment
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    const value = colon === -1 ? "" : line.slice(colon + 1).replace(/^ /, "");
    if (field === "event") name = value;
    else if (field === "data") data.push(value);
  }
  if (!KNOWN.has(name) || data.length === 0) return null;
  try {
    return { event: name, data: JSON.parse(data.join("\n")) } as ChatEvent;
  } catch {
    return null;
  }
}

const authFetch = createAuthFetch(session);

/**
 * Sends the question and calls `onEvent` for each event, in order. Resolves when the stream
 * ends. Throws ApiError if the API refuses the question (422, 429, 503...) before answering.
 */
export async function askQuestion(
  organizationId: string,
  question: string,
  onEvent: (event: ChatEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await authFetch(
    new Request(`${window.location.origin}/api/v1/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        "X-Organization-Id": organizationId,
      },
      body: JSON.stringify({ question }),
      signal,
    }),
  );
  if (!response.ok || !response.body) {
    throw apiError(response.status, await response.json().catch(() => null)) satisfies ApiError;
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  const parser = new SseParser();
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    for (const event of parser.push(value)) onEvent(event);
  }
}

export type AnswerPart = { text: string } | { marker: number };

/** Splits the answer into text and citation markers, so each [n] can be drawn as a badge. */
export function splitCitations(answer: string): AnswerPart[] {
  const parts: AnswerPart[] = [];
  let last = 0;
  for (const match of answer.matchAll(/\[(\d{1,3})\]/g)) {
    if (match.index > last) parts.push({ text: answer.slice(last, match.index) });
    parts.push({ marker: Number(match[1]) });
    last = match.index + match[0].length;
  }
  if (last < answer.length) parts.push({ text: answer.slice(last) });
  return parts;
}
