/**
 * AI tutor UI: an "Explain this" button for answered questions, and the shared status hook.
 * Explanations are requested by interaction id, so they exist only AFTER the student has
 * answered. Every AI text carries the "AI-generated" label from the server.
 */
import { useEffect, useState } from "react";
import { Bot, Sparkles } from "lucide-react";
import { ApiError } from "../api/client";
import { tutor } from "../api/tutor";
import type { AiStatus, AiText } from "../api/tutor";
import { Markdown } from "./Markdown";
import { Button, cx } from "./ui";

let statusPromise: Promise<AiStatus | null> | null = null;

export function resetAiStatus() {
  statusPromise = null;
}

/** Whether the AI tutor is switched on (fetched once per page load). */
export function useAiEnabled(): boolean {
  const [enabled, setEnabled] = useState(false);
  useEffect(() => {
    let alive = true;
    statusPromise ??= tutor.aiStatus().catch(() => null);
    void statusPromise.then((s) => alive && setEnabled(Boolean(s?.enabled)));
    return () => {
      alive = false;
    };
  }, []);
  return enabled;
}

export function AiLabel({ text, model }: { text: string; model?: string }) {
  return (
    <p className="mt-3 flex items-start gap-1.5 text-[11px] leading-4 text-ink-faint">
      <Bot className="mt-px size-3.5 shrink-0" />
      <span>
        {text}
        {model ? ` (${model})` : ""}
      </span>
    </p>
  );
}

export function AiExplain({ interactionId, label = "Explain this step by step", className }: { interactionId: number; label?: string; className?: string }) {
  const enabled = useAiEnabled();
  const [loading, setLoading] = useState(false);
  const [text, setText] = useState<AiText | null>(null);
  const [error, setError] = useState<string>();

  useEffect(() => {
    setText(null);
    setError(undefined);
  }, [interactionId]);

  if (!enabled) return null;

  async function ask() {
    setLoading(true);
    setError(undefined);
    try {
      setText(await tutor.aiExplain(interactionId));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The AI tutor couldn't answer. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  if (text) {
    return (
      <div className={cx("rounded-2xl border border-accent/30 bg-accent/8 p-4 animate-rise", className)} aria-live="polite">
        <p className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-accent">
          <Sparkles className="size-3.5" /> AI tutor
        </p>
        <Markdown source={text.content} />
        <AiLabel text={text.label} model={text.model} />
      </div>
    );
  }
  return (
    <div className={className}>
      <Button variant="soft" size="sm" onClick={ask} loading={loading} icon={<Sparkles className="size-4" />}>
        {loading ? "The AI tutor is thinking…" : label}
      </Button>
      {error && (
        <p className="mt-2 text-xs text-developing" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
