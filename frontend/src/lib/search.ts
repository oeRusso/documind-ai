/** Helpers for the search page. */

const STOP_WORDS = new Set([
  "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "al", "a", "en", "y", "o",
  "que", "qué", "por", "para", "con", "sin", "se", "me", "mi", "mis", "es", "son", "lo", "le",
  "les", "su", "sus", "si", "no", "cuál", "cuáles", "cómo", "cuánto", "cuántos", "cuántas", "puedo",
]);

/** Lowercase without accents, so "informacion" matches "Información". */
export function fold(text: string): string {
  return text.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
}

export type Part = { text: string; match: boolean };

/**
 * Split `text` into parts, marking the words that start like a word of the query (4+ letters,
 * stop words ignored): "plazos" in the query marks "plazo" and "Plazos" in the text.
 */
export function highlightTerms(text: string, query: string): Part[] {
  const stems = Array.from(
    new Set(
      fold(query)
        .split(/[^\p{L}\p{N}]+/u)
        .filter((word) => word.length >= 4 && !STOP_WORDS.has(word))
        .map((word) => word.slice(0, Math.max(4, word.length - 2))),
    ),
  );
  if (stems.length === 0) return [{ text, match: false }];
  const parts: Part[] = [];
  for (const piece of text.split(/([\p{L}\p{N}]+)/u)) {
    if (!piece) continue;
    const folded = fold(piece);
    const match = /[\p{L}\p{N}]/u.test(piece) && stems.some((stem) => folded.startsWith(stem));
    const last = parts[parts.length - 1];
    if (last && last.match === match) last.text += piece;
    else parts.push({ text: piece, match });
  }
  return parts;
}
