import { describe, expect, it } from "vitest";

import { excerptMatcher, normalizeForMatch } from "./highlight";

describe("normalizeForMatch", () => {
  it("ignores accents, case and repeated spaces", () => {
    expect(normalizeForMatch("  Período   de PRUEBA ")).toBe("periodo de prueba");
  });
});

describe("excerptMatcher", () => {
  const matches = excerptMatcher("El contrato de trabajo por tiempo indeterminado se entenderá celebrado a prueba…");

  it("matches the pieces of the page that are in the excerpt", () => {
    expect(matches("se entendera celebrado")).toBe(true);
    expect(matches("Tiempo Indeterminado")).toBe(true);
  });

  it("does not match text that is not in the excerpt", () => {
    expect(matches("período de vacaciones")).toBe(false);
  });

  it("skips very short pieces that would light up the whole page", () => {
    expect(matches("de")).toBe(false);
    expect(matches("   ")).toBe(false);
  });
});
