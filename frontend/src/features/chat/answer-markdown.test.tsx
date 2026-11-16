import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AnswerMarkdown } from "./answer-markdown";

function show(text: string) {
  return render(<AnswerMarkdown text={text} renderCitation={(n, key) => <sup key={key}>{n}</sup>} />);
}

describe("AnswerMarkdown", () => {
  it("draws no HTML from the text, no links and no images", () => {
    const { container } = show(
      'Cada 90 días [1]. <img src="https://evil.example/x.png" onerror="alert(1)"> ' +
        "Ver [premio](https://evil.example/premio) ![x](https://evil.example/log)",
    );
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("a")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
    expect(screen.getByText(/onerror/)).toBeInTheDocument(); // shown as text, not run
    expect(screen.getByText("imagen omitida")).toBeInTheDocument();
    expect(screen.getByText("(evil.example)")).toBeInTheDocument();
    expect(container.querySelector("sup")?.textContent).toBe("1");
  });

  it("draws lists and bold text", () => {
    const { container } = show("Requisitos:\n\n1. **Firma** [2]\n2. Fecha");
    expect(container.querySelectorAll("ol li")).toHaveLength(2);
    expect(container.querySelector("strong")?.textContent).toBe("Firma");
  });
});
