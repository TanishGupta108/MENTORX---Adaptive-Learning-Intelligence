/**
 * A small, safe Markdown renderer for learning notes: "### heading", "- bullet", "1. step",
 * **bold**, blank line = paragraph. It builds React elements (never raw HTML), so content
 * written by admins can't inject markup.
 */
import type { ReactNode } from "react";

function inline(text: string, key: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? (
      <strong key={`${key}-${i}`} className="font-semibold text-ink">
        {part.slice(2, -2)}
      </strong>
    ) : (
      part
    ),
  );
}

export function Markdown({ source }: { source: string }) {
  const blocks = source.trim().split(/\n\s*\n/);
  return (
    <div className="space-y-3 text-[15px] leading-7 text-ink/90">
      {blocks.map((block, bi) => {
        const lines = block.split("\n").map((l) => l.trimEnd());
        const out: ReactNode[] = [];
        let list: { ordered: boolean; items: string[] } | null = null;
        const flush = () => {
          if (!list) return;
          const Tag = list.ordered ? "ol" : "ul";
          out.push(
            <Tag key={`l${bi}-${out.length}`} className={list.ordered ? "ml-5 list-decimal space-y-1.5" : "ml-5 list-disc space-y-1.5 marker:text-brand"}>
              {list.items.map((it, ii) => (
                <li key={ii}>{inline(it, `${bi}-${ii}`)}</li>
              ))}
            </Tag>,
          );
          list = null;
        };
        lines.forEach((line, li) => {
          const h = line.match(/^#{2,4}\s+(.*)$/);
          const ul = line.match(/^\s*[-*]\s+(.*)$/);
          const ol = line.match(/^\s*\d+\.\s+(.*)$/);
          if (h) {
            flush();
            out.push(
              <h4 key={`h${bi}-${li}`} className="pt-1 text-sm font-semibold uppercase tracking-wider text-brand">
                {h[1]}
              </h4>,
            );
          } else if (ul || ol) {
            const ordered = Boolean(ol);
            if (list && list.ordered !== ordered) flush();
            list ??= { ordered, items: [] };
            list.items.push((ul ?? ol)![1] ?? "");
          } else if (line.trim()) {
            flush();
            out.push(<p key={`p${bi}-${li}`}>{inline(line, `${bi}-${li}`)}</p>);
          }
        });
        flush();
        return <div key={bi}>{out}</div>;
      })}
    </div>
  );
}
