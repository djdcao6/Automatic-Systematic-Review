import { useEffect, useRef, useState, type DependencyList } from "react";

// Guards against reviewProjectId changing (or refresh() being called again)
// before an in-flight fetch resolves: only the most recently started fetch
// is allowed to apply its result, so a stale response can't overwrite newer
// data.
export function useListResource<T>(
  fetcher: () => Promise<T[]>,
  deps: DependencyList,
  fallbackError: string
): { data: T[]; error: string | null; refresh: () => Promise<void> } {
  const [data, setData] = useState<T[]>([]);
  const [error, setError] = useState<string | null>(null);
  const latestRequest = useRef(0);

  useEffect(() => {
    const requestId = ++latestRequest.current;
    fetcher()
      .then((result) => {
        if (requestId === latestRequest.current) {
          setData(result);
          setError(null);
        }
      })
      .catch(() => {
        if (requestId === latestRequest.current) {
          setError(fallbackError);
        }
      });
    // fetcher intentionally excluded: callers close over their own
    // dependencies and pass them explicitly via `deps`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  async function refresh() {
    const requestId = ++latestRequest.current;
    try {
      const result = await fetcher();
      if (requestId === latestRequest.current) {
        setData(result);
        setError(null);
      }
    } catch {
      if (requestId === latestRequest.current) {
        setError(fallbackError);
      }
    }
  }

  return { data, error, refresh };
}
