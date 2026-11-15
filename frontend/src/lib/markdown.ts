/**
 * Safe Markdown for answers (stage 9). Turns the model's text into a small tree of blocks and
 * inline pieces that React draws as elements, so nothing in the text is ever HTML:
 * - supported: paragraphs, lists (- / * / 1.), headings (#), **bold**, *italic*, `code` and
 *   citation markers [n];
 * - links ([text](url) and bare https://...) become plain text with the address visible: they
 *   are never clickable, so a document cannot make the page open someone else's site;
 * - images (![alt](url)) are never loaded: they become "[imagen omitida]";
 * - raw HTML stays as visible text (React escapes it). The server already removes it
 *   (OutputGuard): this is the second layer.
 * It replaces a Markdown library on purpose: a few dozen lines, no dependency, and nothing that
 * can render HTML by mistake.
 */

export type Inline =
  | { type: "text"; text: string }
  | { type: "bold" | "italic"; children: Inline[] }
  | { type: "code"; text: string }
  | { type: "citation"; marker: number }
  | { type: "link"; text: string; url: string }
  | { type: "image"; alt: string };

export type Block =
  | { type: "paragraph"; content: Inline[] }
  | { type: "heading"; content: Inline[] }
  | { type: "list"; ordered: boolean; items: Inline[][] };

const INLINE =
  /!\[([^\]\n]*)\]\(([^)\n]*)\)|\[([^\]\n]+)\]\((\S+?)\)|\[(\d{1,3})\]|\*\*(.+?)\*\*|`([^`\n]+)`|(?<![\w*])\*(?![\s*])(.+?)(?<![\s*])\*(?![\w*])|(?<!\w)_(?!\s)(.+?)(?<!\s)_(?!\w)|(https?:\/\/[^\s<>()]+[^\s<>().,;:!?])/g;

export function parseInline(text: string): Inline[] {
  const out: Inline[] = [];
  let last = 0;
  for (const m of text.matchAll(INLINE)) {
    if (m.index > last) out.push({ type: "text", text: text.slice(last, m.index) });
    const [, imageAlt, imageUrl, linkText, linkUrl, marker, bold, code, italic, italic2, url] = m;
    if (imageUrl !== undefined) out.push({ type: "image", alt: imageAlt ?? "" });
    else if (linkUrl !== undefined) out.push({ type: "link", text: linkText ?? linkUrl, url: linkUrl });
    else if (marker !== undefined) out.push({ type: "citation", marker: Number(marker) });
    else if (bold !== undefined) out.push({ type: "bold", children: parseInline(bold) });
    else if (code !== undefined) out.push({ type: "code", text: code });
    else if (italic !== undefined || italic2 !== undefined)
      out.push({ type: "italic", children: parseInline(italic ?? italic2 ?? "") });
    else if (url !== undefined) out.push({ type: "link", text: url, url });
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push({ type: "text", text: text.slice(last) });
  return out;
}

const BULLET = /^\s*[-*•]\s+(.*)$/;
const NUMBERED = /^\s*\d{1,3}[.)]\s+(.*)$/;
const HEADING = /^\s*#{1,6}\s+(.*)$/;

export function parseMarkdown(text: string): Block[] {
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  const flush = () => {
    if (paragraph.length) blocks.push({ type: "paragraph", content: parseInline(paragraph.join("\n")) });
    paragraph = [];
  };
  for (const line of text.split("\n")) {
    const bullet = BULLET.exec(line);
    const numbered = bullet ? null : NUMBERED.exec(line);
    const heading = HEADING.exec(line);
    if (bullet || numbered) {
      flush();
      const ordered = Boolean(numbered);
      const item = parseInline((bullet ?? numbered)?.[1] ?? "");
      const previous = blocks.at(-1);
      if (previous?.type === "list" && previous.ordered === ordered) previous.items.push(item);
      else blocks.push({ type: "list", ordered, items: [item] });
    } else if (heading) {
      flush();
      blocks.push({ type: "heading", content: parseInline(heading[1] ?? "") });
    } else if (line.trim() === "") {
      flush();
    } else {
      paragraph.push(line);
    }
  }
  flush();
  return blocks;
}

/** "https://www.ejemplo.com/a/b" -> "www.ejemplo.com" (shown next to a link's text). */
export function hostOf(url: string): string {
  try {
    return new URL(url).host || url;
  } catch {
    return url;
  }
}
