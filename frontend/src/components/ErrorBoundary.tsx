import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";

/** Last-resort error page: a rendering bug shows this instead of a blank screen. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Unhandled UI error", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-4 px-4">
        <h1 className="text-2xl font-semibold">Something went wrong</h1>
        <p className="text-ink-muted">
          The page hit an unexpected error. Your answers are saved on the server, so reloading is
          safe.
        </p>
        <button
          type="button"
          className="min-h-11 rounded-lg bg-brand px-4 font-medium text-brand-ink"
          onClick={() => window.location.reload()}
        >
          Reload
        </button>
      </main>
    );
  }
}
