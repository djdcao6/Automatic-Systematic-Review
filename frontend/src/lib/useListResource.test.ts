import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useListResource } from "./useListResource";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe("useListResource", () => {
  it("loads data on mount", async () => {
    const fetcher = vi.fn().mockResolvedValue(["a", "b"]);

    const { result } = renderHook(() => useListResource(fetcher, [], "Failed to load."));

    await waitFor(() => expect(result.current.data).toEqual(["a", "b"]));
    expect(result.current.error).toBeNull();
  });

  it("sets the fallback error message when the fetch fails", async () => {
    const fetcher = vi.fn().mockRejectedValue(new Error("boom"));

    const { result } = renderHook(() => useListResource(fetcher, [], "Failed to load."));

    await waitFor(() => expect(result.current.error).toBe("Failed to load."));
    expect(result.current.data).toEqual([]);
  });

  it("refetches and clears a prior error when refresh() is called", async () => {
    const fetcher = vi.fn().mockRejectedValueOnce(new Error("boom")).mockResolvedValueOnce(["ok"]);

    const { result } = renderHook(() => useListResource(fetcher, [], "Failed to load."));

    await waitFor(() => expect(result.current.error).toBe("Failed to load."));

    await act(async () => {
      await result.current.refresh();
    });

    expect(result.current.data).toEqual(["ok"]);
    expect(result.current.error).toBeNull();
  });

  it("ignores a stale response that resolves after a dep change kicked off a newer request", async () => {
    const first = deferred<string[]>();
    const second = deferred<string[]>();
    const fetcher = vi.fn().mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);

    const { result, rerender } = renderHook(
      ({ id }: { id: string }) => useListResource(() => fetcher(id), [id], "Failed to load."),
      { initialProps: { id: "project-a" } }
    );

    rerender({ id: "project-b" });

    await act(async () => {
      second.resolve(["b-item"]);
    });
    await waitFor(() => expect(result.current.data).toEqual(["b-item"]));

    await act(async () => {
      first.resolve(["a-item"]);
    });

    expect(result.current.data).toEqual(["b-item"]);
    expect(result.current.error).toBeNull();
  });

  it("ignores a stale rejection that resolves after a newer request already succeeded", async () => {
    const first = deferred<string[]>();
    const second = deferred<string[]>();
    const fetcher = vi.fn().mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);

    const { result, rerender } = renderHook(
      ({ id }: { id: string }) => useListResource(() => fetcher(id), [id], "Failed to load."),
      { initialProps: { id: "project-a" } }
    );

    rerender({ id: "project-b" });

    await act(async () => {
      second.resolve(["b-item"]);
    });
    await waitFor(() => expect(result.current.data).toEqual(["b-item"]));

    await act(async () => {
      first.reject(new Error("stale failure"));
    });

    expect(result.current.data).toEqual(["b-item"]);
    expect(result.current.error).toBeNull();
  });
});
