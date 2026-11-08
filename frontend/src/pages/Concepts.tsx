import { useState } from "react";
import { ConceptMap, LEGEND } from "../components/ConceptMap";
import { Button, Card, cx, ErrorState, MasteryBar, PageHeader, Spinner, toneClass } from "../components/ui";
import { useConcepts } from "../hooks/useConcepts";
import { useStartSession } from "../hooks/useStartSession";

export function ConceptsPage() {
  const concepts = useConcepts();
  const starter = useStartSession();
  const [selected, setSelected] = useState<string>();
  const list = concepts.data ?? [];
  const current = list.find((c) => c.code === selected);
  const byCode = Object.fromEntries(list.map((c) => [c.code, c]));

  return (
    <>
      <PageHeader title="Concepts">
        Arrows run from a prerequisite to the concepts that build on it. Select a concept for
        details.
      </PageHeader>
      {concepts.loading && !concepts.data && <Spinner />}
      {concepts.error && <ErrorState error={concepts.error} onRetry={concepts.reload} />}
      {starter.error && (
        <p role="alert" className="mb-4 text-sm text-danger">
          {starter.error}
        </p>
      )}
      {list.length > 0 && (
        <div className="grid gap-6 xl:grid-cols-[1fr_320px]">
          <Card>
            <ul className="mb-4 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-muted">
              {LEGEND.map((l) => (
                <li key={l.tone} className="flex items-center gap-1.5">
                  <span className={cx("inline-block size-3 rounded-sm", toneClass[l.tone])} />
                  {l.label}
                </li>
              ))}
            </ul>
            <ConceptMap concepts={list} selected={selected} onSelect={setSelected} />
          </Card>
          <Card title={current ? current.name : "All concepts"} className="self-start">
            {current ? (
              <>
                <p className="text-sm text-ink-muted">{current.description}</p>
                <div className="mt-4">
                  <MasteryBar value={current.mastery} label={`${current.name} mastery`} />
                  <p className="mt-1 text-xs text-ink-muted">
                    {current.n_attempts} answer{current.n_attempts === 1 ? "" : "s"} so far
                  </p>
                </div>
                <h3 className="mt-4 text-sm font-medium">Builds on</h3>
                {current.prerequisites.length ? (
                  <ul className="mt-1 space-y-1 text-sm">
                    {current.prerequisites.map((p) => (
                      <li key={p}>
                        <button
                          type="button"
                          className="min-h-8 text-brand underline-offset-2 hover:underline"
                          onClick={() => setSelected(p)}
                        >
                          {byCode[p]?.name ?? p}
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-1 text-sm text-ink-muted">Nothing: it's a starting point.</p>
                )}
                <Button
                  className="mt-5 w-full"
                  disabled={starter.busy !== null}
                  onClick={() => starter.start("practice", current.code)}
                >
                  Practise {current.name}
                </Button>
              </>
            ) : (
              <ul className="space-y-3">
                {list.map((c) => (
                  <li key={c.code}>
                    <button
                      type="button"
                      className="w-full text-left text-sm font-medium hover:text-brand"
                      onClick={() => setSelected(c.code)}
                    >
                      {c.name}
                    </button>
                    <MasteryBar value={c.mastery} label={`${c.name} mastery`} />
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      )}
    </>
  );
}
