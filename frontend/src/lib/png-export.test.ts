import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { downloadElementAsPng } from "./png-export";

describe("downloadElementAsPng", () => {
  let drawImageSpy: ReturnType<typeof vi.fn>;
  let toBlobSpy: ReturnType<typeof vi.fn>;
  let createObjectURLSpy: ReturnType<typeof vi.fn>;
  let revokeObjectURLSpy: ReturnType<typeof vi.fn>;
  let clickSpy: ReturnType<typeof vi.fn>;

  class FakeImage {
    onload: (() => void) | null = null;
    onerror: (() => void) | null = null;
    set src(_value: string) {
      queueMicrotask(() => this.onload?.());
    }
  }

  beforeEach(() => {
    drawImageSpy = vi.fn();
    toBlobSpy = vi.fn((callback: (blob: Blob | null) => void) => {
      callback(new Blob(["fake-png"], { type: "image/png" }));
    });
    createObjectURLSpy = vi.fn(() => "blob:fake-url");
    revokeObjectURLSpy = vi.fn();
    clickSpy = vi.fn();

    vi.stubGlobal("Image", FakeImage);
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: createObjectURLSpy,
      revokeObjectURL: revokeObjectURLSpy,
    });

    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
      drawImage: drawImageSpy,
    } as unknown as CanvasRenderingContext2D);
    vi.spyOn(HTMLCanvasElement.prototype, "toBlob").mockImplementation(
      toBlobSpy as unknown as (callback: BlobCallback, type?: string, quality?: number) => void
    );
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(
      clickSpy as unknown as () => void
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("rasterizes the element onto a canvas sized to its rendered bounds", async () => {
    const element = document.createElement("div");
    element.innerHTML = "<p>diagram</p>";
    document.body.appendChild(element);
    vi.spyOn(element, "getBoundingClientRect").mockReturnValue({
      width: 640,
      height: 480,
    } as DOMRect);

    await downloadElementAsPng(element, "prisma-flow-diagram.png");

    expect(drawImageSpy).toHaveBeenCalledWith(expect.any(FakeImage), 0, 0, 640, 480);
    element.remove();
  });

  it("triggers a browser download of the rasterized PNG with the given filename", async () => {
    const element = document.createElement("div");
    vi.spyOn(element, "getBoundingClientRect").mockReturnValue({
      width: 100,
      height: 50,
    } as DOMRect);

    await downloadElementAsPng(element, "prisma-flow-diagram.png");

    expect(toBlobSpy).toHaveBeenCalled();
    expect(createObjectURLSpy).toHaveBeenCalledWith(expect.any(Blob));
    expect(clickSpy).toHaveBeenCalledTimes(1);
    expect(revokeObjectURLSpy).toHaveBeenCalledWith("blob:fake-url");
  });

  it("rejects when the canvas cannot produce a PNG blob", async () => {
    toBlobSpy.mockImplementation((callback: (blob: Blob | null) => void) => callback(null));
    const element = document.createElement("div");
    vi.spyOn(element, "getBoundingClientRect").mockReturnValue({
      width: 100,
      height: 50,
    } as DOMRect);

    await expect(downloadElementAsPng(element, "prisma-flow-diagram.png")).rejects.toThrow(
      /failed to rasterize/i
    );
  });
});
