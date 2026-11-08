import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../api/client";

export type ApiState<T> = {
  data: T | undefined;
  error: ApiError | Error | undefined;
  loading: boolean;
  reload: () => void;
};

/** Load data from the API; aborts on unmount and when `deps` change. */
export function useApi<T>(load: (signal: AbortSignal) => Promise<T>, deps: unknown[] = []) {
  const [state, setState] = useState<Omit<ApiState<T>, "reload">>({
    data: undefined,
    error: undefined,
    loading: true,
  });
  const [tick, setTick] = useState(0);
  const loadRef = useRef(load);
  loadRef.current = load;

  useEffect(() => {
    const ctrl = new AbortController();
    setState((s) => ({ ...s, loading: true, error: undefined }));
    loadRef
      .current(ctrl.signal)
      .then((data) => {
        if (!ctrl.signal.aborted) setState({ data, error: undefined, loading: false });
      })
      .catch((error: unknown) => {
        if (ctrl.signal.aborted) return;
        setState((s) => ({
          ...s,
          error: error instanceof Error ? error : new Error(String(error)),
          loading: false,
        }));
      });
    return () => ctrl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tick, ...deps]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { ...state, reload } as ApiState<T>;
}
