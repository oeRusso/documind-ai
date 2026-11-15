import { describe, expect, it } from "vitest";

import { hostOf, parseInline, parseMarkdown } from "./markdown";

describe("parseInline", () => {
  it("keeps citations, bold, italic and code", () => {
    expect(parseInline("El plazo es **30 días** [1] y *no* `corre`.")).toEqual([
      { type: "text", text: "El plazo es " },
      { type: "bold", children: [{ type: "text", text: "30 días" }] },
      { type: "text", text: " " },
      { type: "citation", marker: 1 },
      { type: "text", text: " y " },
      { type: "italic", children: [{ type: "text", text: "no" }] },
      { type: "text", text: " " },
      { type: "code", text: "corre" },
      { type: "text", text: "." },
    ]);
  });

  it("never loads images: they become an omitted marker", () => {
    expect(parseInline("![logo](https://evil.example/log?q=hola)")).toEqual([{ type: "image", alt: "logo" }]);
  });

  it("turns links into text with their address, never into anchors", () => {
    expect(parseInline("Ver [el sitio](https://evil.example/premio).")).toEqual([
      { type: "text", text: "Ver " },
      { type: "link", text: "el sitio", url: "https://evil.example/premio" },
      { type: "text", text: "." },
    ]);
    expect(parseInline("En https://www.argentina.gob.ar/x.")).toEqual([
      { type: "text", text: "En " },
      { type: "link", text: "https://www.argentina.gob.ar/x", url: "https://www.argentina.gob.ar/x" },
      { type: "text", text: "." },
    ]);
  });

  it("leaves raw HTML as plain text (React escapes it)", () => {
    expect(parseInline('<img src="x" onerror="alert(1)">')).toEqual([
      { type: "text", text: '<img src="x" onerror="alert(1)">' },
    ]);
  });

  it("does not take multiplications or snake_case for italics", () => {
    expect(parseInline("2 * 3 * 4 y nombre_de_archivo")).toEqual([
      { type: "text", text: "2 * 3 * 4 y nombre_de_archivo" },
    ]);
  });
});

describe("parseMarkdown", () => {
  it("builds paragraphs, lists and headings", () => {
    const blocks = parseMarkdown("## Requisitos\nSon dos:\n\n1. Firma [1]\n2. Fecha\n- suelto");
    expect(blocks.map((b) => b.type)).toEqual(["heading", "paragraph", "list", "list"]);
    const ordered = blocks[2];
    expect(ordered).toMatchObject({ type: "list", ordered: true });
    expect(ordered?.type === "list" && ordered.items.length).toBe(2);
  });
});

describe("hostOf", () => {
  it("shows only the host", () => {
    expect(hostOf("https://evil.example/premio?x=1")).toBe("evil.example");
    expect(hostOf("no es url")).toBe("no es url");
  });
});
