/**
 * Which pieces of a PDF page to highlight for a citation (stage 8).
 *
 * pdf.js draws the page's text as many small invisible <span>s on top of the image (the "text
 * layer"). The citation brings an excerpt of the chunk. A span is highlighted when its text is
 * part of the excerpt, comparing without accents, case or extra spaces. Very short spans ("a",
 * "de") are skipped: they appear everywhere and would light up the whole page.
 */

const MIN_CHARS = 4;

export function normalizeForMatch(text: string): string {
  return text
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase()
    .replace(/[\s­]+/g, " ")
    .trim();
}

/** Builds the test once per excerpt; call it for each span of the page. */
export function excerptMatcher(excerpt: string): (spanText: string) => boolean {
  // The excerpt ends with "…" when it was cut: that character is not in the document.
  const target = normalizeForMatch(excerpt.replace(/…$/, ""));
  return (spanText: string) => {
    const piece = normalizeForMatch(spanText);
    return piece.length >= MIN_CHARS && target.includes(piece);
  };
}
