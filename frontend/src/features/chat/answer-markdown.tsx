"use client";

/** Draws an answer's safe Markdown (lib/markdown.ts): elements only, never HTML (stage 9). */

import { ImageOff } from "lucide-react";
import type { ReactNode } from "react";

import { hostOf, parseMarkdown, type Inline } from "@/lib/markdown";

export function AnswerMarkdown({
  text,
  renderCitation,
  cursor,
}: {
  text: string;
  renderCitation: (marker: number, key: string) => ReactNode;
  cursor?: ReactNode;
}) {
  const blocks = parseMarkdown(text);
  return (
    <div className="grid gap-3 leading-relaxed">
      {blocks.map((block, i) => {
        const last = i === blocks.length - 1;
        if (block.type === "list") {
          const List = block.ordered ? "ol" : "ul";
          return (
            <List key={i} className={block.ordered ? "ml-5 list-decimal space-y-1" : "ml-5 list-disc space-y-1"}>
              {block.items.map((item, j) => (
                <li key={j}>
                  {inlines(item, renderCitation, `${i}.${j}`)}
                  {last && j === block.items.length - 1 && cursor}
                </li>
              ))}
            </List>
          );
        }
        return (
          <p key={i} className={block.type === "heading" ? "font-semibold" : "whitespace-pre-line"}>
            {inlines(block.content, renderCitation, String(i))}
            {last && cursor}
          </p>
        );
      })}
      {blocks.length === 0 && cursor}
    </div>
  );
}

function inlines(items: Inline[], renderCitation: (marker: number, key: string) => ReactNode, prefix: string) {
  return items.map((item, i) => {
    const key = `${prefix}.${i}`;
    switch (item.type) {
      case "text":
        return <span key={key}>{item.text}</span>;
      case "bold":
        return <strong key={key}>{inlines(item.children, renderCitation, key)}</strong>;
      case "italic":
        return <em key={key}>{inlines(item.children, renderCitation, key)}</em>;
      case "code":
        return (
          <code key={key} className="rounded bg-muted px-1 font-mono text-[0.9em]">
            {item.text}
          </code>
        );
      case "citation":
        return renderCitation(item.marker, key);
      case "link":
        // Never an <a>: the address is visible and the person decides whether to copy it.
        return (
          <span key={key} title={item.url} className="underline decoration-dotted underline-offset-2">
            {item.text}
            {item.text !== item.url && <span className="text-muted-foreground"> ({hostOf(item.url)})</span>}
          </span>
        );
      case "image":
        return (
          <span
            key={key}
            className="inline-flex items-center gap-1 rounded bg-muted px-1.5 text-xs text-muted-foreground"
            title="Las imágenes de las respuestas no se cargan"
          >
            <ImageOff className="size-3" />
            imagen omitida
          </span>
        );
    }
  });
}
