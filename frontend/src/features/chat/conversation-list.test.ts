import { describe, expect, it } from "vitest";

import { shortWhen } from "./conversation-list";

describe("shortWhen", () => {
  const now = new Date(2026, 10, 16, 15, 0);

  it("shows only the time for today", () => {
    expect(shortWhen(new Date(2026, 10, 16, 9, 5).toISOString(), now)).toBe("09:05");
  });

  it("shows day and month for this year, without the abbreviation dot", () => {
    expect(shortWhen(new Date(2026, 10, 2, 9, 5).toISOString(), now)).toBe("2 nov");
  });

  it("adds the year for older dates", () => {
    expect(shortWhen(new Date(2025, 0, 20).toISOString(), now)).toBe("20 ene 2025");
  });
});
