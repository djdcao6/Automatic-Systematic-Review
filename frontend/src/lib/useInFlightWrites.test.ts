import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useInFlightWrites } from "./useInFlightWrites";

function deferred() {
  let resolve!: () => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<void>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const is = (wanted: string) => (key: string) => key === wanted;

describe("useInFlightWrites", () => {
  it("turns away a second write with the same key made in the same tick", async () => {
    const { result } = renderHook(() => useInFlightWrites());
    const first = deferred();
    const write = vi.fn(() => first.promise);
    let calls: Promise<void>[] = [];

    act(() => {
      calls = [result.current.run("save", write), result.current.run("save", write)];
    });

    expect(write).toHaveBeenCalledTimes(1);
    await act(async () => {
      first.resolve();
      await Promise.all(calls);
    });
  });

  it("lets writes with different keys run together", async () => {
    const { result } = renderHook(() => useInFlightWrites());
    const a = deferred();
    const b = deferred();
    const writeA = vi.fn(() => a.promise);
    const writeB = vi.fn(() => b.promise);
    let calls: Promise<void>[] = [];

    act(() => {
      calls = [result.current.run("a", writeA), result.current.run("b", writeB)];
    });

    expect(writeA).toHaveBeenCalledTimes(1);
    expect(writeB).toHaveBeenCalledTimes(1);
    await act(async () => {
      a.resolve();
      b.resolve();
      await Promise.all(calls);
    });
  });

  it("says at once what is running, and after a render what is pending", async () => {
    const { result } = renderHook(() => useInFlightWrites());
    const write = deferred();
    let call: Promise<void> = Promise.resolve();

    expect(result.current.isRunning(is("save"))).toBe(false);
    expect(result.current.isPending(is("save"))).toBe(false);

    act(() => {
      call = result.current.run("save", () => write.promise);
      // Before any re-render: the guard already knows, the screen does not yet.
      expect(result.current.isRunning(is("save"))).toBe(true);
    });

    expect(result.current.isPending(is("save"))).toBe(true);
    expect(result.current.isPending(is("other"))).toBe(false);

    await act(async () => {
      write.resolve();
      await call;
    });

    expect(result.current.isRunning(is("save"))).toBe(false);
    expect(result.current.isPending(is("save"))).toBe(false);
  });

  it("lets the key be used again after the write fails", async () => {
    const { result } = renderHook(() => useInFlightWrites());
    const write = vi.fn().mockRejectedValueOnce(new Error("boom")).mockResolvedValueOnce(undefined);

    await act(async () => {
      await expect(result.current.run("save", write)).rejects.toThrow("boom");
    });
    expect(result.current.isRunning(is("save"))).toBe(false);

    await act(async () => {
      await result.current.run("save", write);
    });

    expect(write).toHaveBeenCalledTimes(2);
  });
});
