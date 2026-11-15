import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { formatDay, niceMax, QuestionsChart } from "./questions-chart";

describe("questions chart", () => {
  it("rounds the top of the axis", () => {
    expect([niceMax(0), niceMax(1), niceMax(3), niceMax(7), niceMax(12), niceMax(51)]).toEqual([1, 1, 5, 10, 20, 100]);
  });

  it("shows days as day/month", () => {
    expect(formatDay("2026-11-05")).toBe("5/11");
  });

  it("has a bar and an accessible label per day, and a table", () => {
    const points = [
      { day: "2026-11-14", questions: 2 },
      { day: "2026-11-15", questions: 5 },
    ];
    const { container } = render(<QuestionsChart points={points} />);
    expect(container.querySelectorAll("rect")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "15/11: 5 preguntas" })).toBeInTheDocument();
    expect(container.querySelectorAll("tbody tr")).toHaveLength(2);
  });
});
