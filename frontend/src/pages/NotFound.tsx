import { ButtonLink } from "../components/ui";

export function NotFoundPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-4 px-4">
      <p className="text-sm font-medium text-brand">404</p>
      <h1 className="text-2xl font-semibold">Page not found</h1>
      <p className="text-ink-muted">That page doesn't exist. It may have moved.</p>
      <ButtonLink to="/" className="self-start">
        Go home
      </ButtonLink>
    </main>
  );
}
