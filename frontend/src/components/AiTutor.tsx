/**
 * AI tutor UI: the shared status hook, the "Explain with AI" button for answered questions, and
 * the error/retry block. Explanations are requested by interaction id, so they exist only AFTER
 * the student has answered. Every AI text carries the "AI-generated" label from the server.
 */
import { useEffect, useState } from "react";
import { Bot, RefreshCw, Sparkles } from "lucide-react";
import { ApiError } from "../api/client";
import { tutor } from "../api/tutor";
import type { AiStatus, AiText } from "../api/tutor";
import { Markdown } from "./Markdown";
import { Button, cx } from "./ui";

export const AI_THINKING = "Thinking… this can take up to 30 seconds";

// The status is shared by every AI button on the page. A good answer is reused for a minute;
// a failed or empty one is fetched again by the next button that mounts.
const STATUS_TTL_MS = 60_000;
let cached: { at: number; promise: Promise<AiStatus | null>; value?: AiStatus | null } | null = null;

export function resetAiStatus() {
  cached = null;
}

/** Forget the cached status (e.g. after the server said the AI key was rejected). */
export function invalidateAiStatus() {
  cached = null;
}

function loadStatus(): Promise<AiStatus | null> {
  const fresh = cached && cached.value !== null && Date.now() - cached.at < STATUS_TTL_MS;
  if (cached && (fresh || cached.value === undefined)) return cached.promise;
  const entry: NonNullable<typeof cached> = {
    at: Date.now(),
    promise: tutor
      .aiStatus()
      .catch(() => null)
      .then((s) => {
        entry.value = s;
        return s;
      }),
  };
  cached = entry;
  return entry.promise;
}

export function useAiStatus(): AiStatus | null {
  const [status, setStatus] = useState<AiStatus | null>(cached?.value ?? null);
  useEffect(() => {
    let alive = true;
    void loadStatus().then((s) => alive && setStatus(s));
    return () => {
      alive = false;
    };
  }, []);
  return status;
}

/** Whether the AI tutor is switched on (and its key wasn't rejected). */
export function useAiEnabled(): boolean {
  const s = useAiStatus();
  return Boolean(s?.enabled) && s?.key_ok !== false;
}

/** Errors that a retry can't fix. */
const FINAL_CODES = new Set(["ai_key_rejected", "ai_disabled", "ai_daily_limit"]);

export type AiError = { message: string; retryable: boolean };

export function toAiError(e: unknown): AiError {
  if (e instanceof ApiError) {
    if (e.code === "ai_key_rejected") invalidateAiStatus();
    return { message: e.code === "ai_key_rejected" ? "The AI tutor isn't available right now." : e.message, retryable: !FINAL_CODES.has(e.code) };
  }
  return { message: "The AI tutor couldn't answer. Please try again.", retryable: true };
}

export function AiErrorNote({ error, onRetry, retryLabel = "Try again" }: { error: AiError; onRetry: () => void; retryLabel?: string }) {
  return (
    <div className="mt-2 flex flex-wrap items-center gap-2" role="alert">
      <p className="text-sm text-developing">{error.message}</p>
      {error.retryable && (
        <Button variant="secondary" size="sm" onClick={onRetry} icon={<RefreshCw className="size-3.5" />}>
          {retryLabel}
        </Button>
      )}
    </div>
  );
}

export function AiLabel({ text, model }: { text: string; model?: string }) {
  return (
    <p className="mt-3 flex items-start gap-1.5 text-[11px] leading-4 text-ink-faint">
      <Bot className="mt-px size-3.5 shrink-0" aria-hidden />
      <span>
        {text}
        {model ? ` (${model})` : ""}
      </span>
    </p>
  );
}

export function AiExplain({ interactionId, label = "Explain with AI", className }: { interactionId: number; label?: string; className?: string }) {
  const enabled = useAiEnabled();
  const [loading, setLoading] = useState(false);
  const [text, setText] = useState<AiText | null>(null);
  const [error, setError] = useState<AiError>();

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
      setError(toAiError(e));
    } finally {
      setLoading(false);
    }
  }

  if (text) {
    return (
      <div className={cx("rounded-xl bg-surface-2 p-4 animate-rise", className)} aria-live="polite">
        <p className="mb-2 flex items-center gap-2 text-sm font-medium text-ink-muted">
          <Sparkles className="size-3.5" aria-hidden /> AI tutor
        </p>
        <Markdown source={text.content} />
        <AiLabel text={text.label} model={text.model} />
      </div>
    );
  }
  return (
    <div className={className}>
      {!error && (
        <Button variant="soft" size="sm" onClick={ask} loading={loading} icon={<Sparkles className="size-4" />}>
          {loading ? AI_THINKING : label}
        </Button>
      )}
      {error && <AiErrorNote error={error} onRetry={ask} />}
    </div>
  );
}
