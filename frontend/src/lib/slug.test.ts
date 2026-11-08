import { describe, expect, it } from "vitest";

import { slugify } from "./slug";

describe("slugify", () => {
  it("makes a valid slug from a company name", () => {
    expect(slugify("Acme S.A.")).toBe("acme-s-a");
    expect(slugify("  Compañía Ñandú 2026 ")).toBe("compania-nandu-2026");
    expect(slugify("x".repeat(80))).toHaveLength(63);
  });
});
