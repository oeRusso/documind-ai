import { describe, expect, it } from "vitest";

import { fold, highlightTerms } from "./search";

const marked = (text: string, query: string) =>
  highlightTerms(text, query)
    .filter((part) => part.match)
    .map((part) => part.text);

describe("highlightTerms", () => {
  it("marks words that start like the query's, ignoring accents and case", () => {
    expect(marked("El plazo de preaviso es de treinta días.", "plazos de preaviso")).toEqual([
      "plazo",
      "preaviso",
    ]);
    expect(marked("Acceso a la Información Pública", "informacion publica")).toEqual([
      "Información",
      "Pública",
    ]);
  });

  it("ignores short and stop words", () => {
    expect(marked("Que el empleado de la empresa", "¿qué es el de?")).toEqual([]);
  });

  it("keeps the whole text", () => {
    const text = "Artículo 245. Indemnización por despido.";
    expect(
      highlightTerms(text, "indemnizacion despido")
        .map((part) => part.text)
        .join(""),
    ).toBe(text);
  });

  it("folds accents", () => {
    expect(fold("Información ÁÉÍÓÚ")).toBe("informacion aeiou");
  });
});
