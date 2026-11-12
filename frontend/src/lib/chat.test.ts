import { describe, expect, it } from "vitest";

import { SseParser, splitCitations } from "./chat";

describe("SseParser", () => {
  it("reads whole events in order", () => {
    const parser = new SseParser();
    const events = parser.push(
      'event: token\ndata: {"text":"Hola"}\n\nevent: done\ndata: {"no_evidence":false}\n\n',
    );
    expect(events).toEqual([
      { event: "token", data: { text: "Hola" } },
      { event: "done", data: { no_evidence: false } },
    ]);
  });

  it("joins an event cut in several pieces", () => {
    const parser = new SseParser();
    expect(parser.push("event: tok")).toEqual([]);
    expect(parser.push('en\ndata: {"text":"30 dí')).toEqual([]);
    expect(parser.push('as [1]"}\n')).toEqual([]);
    expect(parser.push("\n")).toEqual([{ event: "token", data: { text: "30 días [1]" } }]);
  });

  it("ignores keep-alive comments and unknown events", () => {
    const parser = new SseParser();
    const events = parser.push(
      ': ping\n\nevent: other\ndata: {}\n\nevent: queued\ndata: {"position":2}\n\n',
    );
    expect(events).toEqual([{ event: "queued", data: { position: 2 } }]);
  });

  it("accepts CRLF line endings", () => {
    const parser = new SseParser();
    expect(parser.push('event: done\r\ndata: {"no_evidence":true}\r\n\r\n')).toEqual([
      { event: "done", data: { no_evidence: true } },
    ]);
  });
});

describe("splitCitations", () => {
  it("separates the markers from the text", () => {
    expect(splitCitations("Son 30 días [1]. Y doble [1][2].")).toEqual([
      { text: "Son 30 días " },
      { marker: 1 },
      { text: ". Y doble " },
      { marker: 1 },
      { marker: 2 },
      { text: "." },
    ]);
  });

  it("leaves other brackets as text", () => {
    expect(splitCitations("Inciso [a] y rango [1-3]")).toEqual([{ text: "Inciso [a] y rango [1-3]" }]);
  });
});
