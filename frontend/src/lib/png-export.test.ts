import { readFileSync } from "node:fs";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { downloadElementAsPng, LIGHT_TOKENS } from "./png-export";

const DARK_SURFACE = "#171b23";

const SVG_DATA_URL_PREFIX = "data:image/svg+xml;charset=utf-8,";

/** A stylesheet's @font-face rule, as far as the export reads it. */
function fontFaceRule(family: string, file: string, unicodeRange = "") {
  const descriptors: Record<string, string> = {
    "font-family": `"${family}"`,
    "unicode-range": unicodeRange,
  };
  return {
    cssText: `@font-face { font-family: "${family}"; src: url("/media/${file}") format("woff2"); }`,
    style: { getPropertyValue: (name: string) => descriptors[name] ?? "" },
  };
}

function stubStyleSheet(
  rules: ReturnType<typeof fontFaceRule>[],
  href = "http://localhost/_next/static/css/app.css"
) {
  vi.spyOn(document, "styleSheets", "get").mockReturnValue([
    { href, cssRules: rules },
  ] as unknown as StyleSheetList);
}

function stubFontFetch() {
  const fetchSpy = vi.fn<(url: string) => Promise<{ ok: boolean; blob: () => Promise<Blob> }>>(
    async () => ({
      ok: true,
      blob: async () => new Blob(["font-bytes"], { type: "font/woff2" }),
    })
  );
  vi.stubGlobal("fetch", fetchSpy);
  return fetchSpy;
}

/**
 * jsdom does not resolve var() or cascade prefers-color-scheme, so stand in for
 * the browser: an element's `data-background` names the custom property its
 * background uses (as `background: var(<name>)` would), resolved against the
 * properties set inline on it or an ancestor (they inherit), falling back to
 * the dark theme's value, the way the page's stylesheet would.
 */
function fakeComputedStyle(element: Element, fontFamily = "Georgia, serif") {
  const token = element.getAttribute("data-background") ?? undefined;
  let inline = "";
  for (let node: Element | null = element; token && node && !inline; node = node.parentElement) {
    inline = (node as HTMLElement).style.getPropertyValue(token);
  }
  const properties: Record<string, string> = {
    "background-color": token ? inline || DARK_SURFACE : "transparent",
    "font-family": fontFamily,
    height: "46px",
  };
  const names = Object.keys(properties);
  return Object.assign(names, {
    getPropertyValue: (name: string) => properties[name] ?? "",
  }) as unknown as CSSStyleDeclaration;
}

describe("downloadElementAsPng", () => {
  let drawImageSpy: ReturnType<typeof vi.fn>;
  let fillRectSpy: ReturnType<typeof vi.fn>;
  let toBlobSpy: ReturnType<typeof vi.fn>;
  let createObjectURLSpy: ReturnType<typeof vi.fn>;
  let revokeObjectURLSpy: ReturnType<typeof vi.fn>;
  let clickSpy: ReturnType<typeof vi.fn>;
  const originalCreateObjectURL = URL.createObjectURL;
  const originalRevokeObjectURL = URL.revokeObjectURL;

  class FakeImage {
    static sources: string[] = [];
    onload: (() => void) | null = null;
    onerror: (() => void) | null = null;
    set src(value: string) {
      FakeImage.sources.push(value);
      queueMicrotask(() => this.onload?.());
    }
  }

  function sizedElement(width = 100, height = 50) {
    const element = document.createElement("div");
    vi.spyOn(element, "getBoundingClientRect").mockReturnValue({ width, height } as DOMRect);
    return element;
  }

  function useFakeComputedStyle(fontFamily?: string) {
    vi.spyOn(window, "getComputedStyle").mockImplementation((target) =>
      fakeComputedStyle(target, fontFamily)
    );
  }

  /** The SVG that was rasterized, decoded from the data: URL the image loaded. */
  function exportedSvg(): string {
    return decodeURIComponent(FakeImage.sources[0].slice(SVG_DATA_URL_PREFIX.length));
  }

  beforeEach(() => {
    drawImageSpy = vi.fn();
    fillRectSpy = vi.fn();
    toBlobSpy = vi.fn((callback: (blob: Blob | null) => void) => {
      callback(new Blob(["fake-png"], { type: "image/png" }));
    });
    createObjectURLSpy = vi.fn(() => "blob:fake-url");
    revokeObjectURLSpy = vi.fn();
    clickSpy = vi.fn();

    FakeImage.sources = [];
    vi.stubGlobal("Image", FakeImage);
    URL.createObjectURL = createObjectURLSpy as unknown as typeof URL.createObjectURL;
    URL.revokeObjectURL = revokeObjectURLSpy as unknown as typeof URL.revokeObjectURL;

    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
      drawImage: drawImageSpy,
      fillRect: fillRectSpy,
    } as unknown as CanvasRenderingContext2D);
    vi.spyOn(HTMLCanvasElement.prototype, "toBlob").mockImplementation(
      toBlobSpy as unknown as (callback: BlobCallback, type?: string, quality?: number) => void
    );
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(
      clickSpy as unknown as () => void
    );
  });

  afterEach(() => {
    URL.createObjectURL = originalCreateObjectURL;
    URL.revokeObjectURL = originalRevokeObjectURL;
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
    const element = sizedElement();

    await downloadElementAsPng(element, "prisma-flow-diagram.png");

    expect(toBlobSpy).toHaveBeenCalled();
    expect(createObjectURLSpy).toHaveBeenCalledWith(expect.any(Blob));
    expect(clickSpy).toHaveBeenCalledTimes(1);
    expect(revokeObjectURLSpy).toHaveBeenCalledWith("blob:fake-url");
  });

  it("rejects when the canvas cannot produce a PNG blob", async () => {
    toBlobSpy.mockImplementation((callback: (blob: Blob | null) => void) => callback(null));
    const element = sizedElement();

    await expect(downloadElementAsPng(element, "prisma-flow-diagram.png")).rejects.toThrow(
      /failed to rasterize/i
    );
  });

  it("paints an opaque light ground before drawing the diagram", async () => {
    const element = sizedElement(320, 200);

    await downloadElementAsPng(element, "prisma-flow-diagram.png");

    expect(fillRectSpy).toHaveBeenCalledWith(0, 0, 320, 200);
    expect(fillRectSpy.mock.invocationCallOrder[0]).toBeLessThan(
      drawImageSpy.mock.invocationCallOrder[0]
    );
  });

  describe("styling the export", () => {
    it("carries resolved light-theme colours and no unresolved var()", async () => {
      const element = sizedElement();
      element.innerHTML = '<p data-background="--surface">Duplicates removed: 1</p>';
      useFakeComputedStyle();

      await downloadElementAsPng(element, "prisma-flow-diagram.png");

      const svg = exportedSvg();
      expect(svg).toContain("Duplicates removed: 1");
      expect(svg).toContain(`background-color:${LIGHT_TOKENS["--surface"]}`);
      expect(svg).not.toContain(DARK_SURFACE);
      expect(svg).not.toMatch(/var\(--/);
    });

    it("leaves the live element's own inline style as it found it", async () => {
      const styled = sizedElement();
      styled.setAttribute("style", "padding: 4px;");
      const unstyled = sizedElement();
      useFakeComputedStyle();

      await downloadElementAsPng(styled, "a.png");
      await downloadElementAsPng(unstyled, "b.png");

      expect(styled.getAttribute("style")).toBe("padding: 4px;");
      expect(unstyled.hasAttribute("style")).toBe(false);
    });

    it("restores the live element's style even when reading styles throws", async () => {
      const element = sizedElement();
      vi.spyOn(window, "getComputedStyle").mockImplementation(() => {
        throw new Error("boom");
      });

      await expect(downloadElementAsPng(element, "a.png")).rejects.toThrow("boom");

      expect(element.hasAttribute("style")).toBe(false);
    });

    it("drops the page's margin and shadow from the exported root", async () => {
      const element = sizedElement();
      useFakeComputedStyle();

      await downloadElementAsPng(element, "prisma-flow-diagram.png");

      const svg = exportedSvg();
      expect(svg).toMatch(/margin:\s*0/);
      expect(svg).toMatch(/box-shadow:\s*none/);
    });

    it("does not pin used heights, which would grow collapsed-border table rows", async () => {
      const element = sizedElement();
      useFakeComputedStyle();

      await downloadElementAsPng(element, "prisma-flow-diagram.png");

      expect(exportedSvg()).not.toContain("height:46px");
    });

    it("rounds fractional bounds up so the last pixel row is not clipped", async () => {
      const element = sizedElement(640.4, 480.06);

      await downloadElementAsPng(element, "prisma-flow-diagram.png");

      expect(drawImageSpy).toHaveBeenCalledWith(expect.any(FakeImage), 0, 0, 641, 481);
    });

    it("loads the SVG from a data: URL, since a blob: URL taints the canvas in Chrome", async () => {
      const element = sizedElement();

      await downloadElementAsPng(element, "prisma-flow-diagram.png");

      expect(FakeImage.sources).toHaveLength(1);
      expect(FakeImage.sources[0].startsWith(SVG_DATA_URL_PREFIX)).toBe(true);
      expect(createObjectURLSpy).toHaveBeenCalledTimes(1); // only the finished PNG
    });

    it("embeds the web fonts the diagram uses as data URIs", async () => {
      const element = sizedElement();
      useFakeComputedStyle('"Plate Serif", "Plate Serif Fallback", Georgia, serif');
      stubStyleSheet(
        [fontFaceRule("Plate Serif", "serif.woff2"), fontFaceRule("Unused Face", "unused.woff2")],
        "http://localhost/_next/static/css/app.css"
      );
      const fetchSpy = stubFontFetch();

      await downloadElementAsPng(element, "prisma-flow-diagram.png");

      const svg = exportedSvg();
      expect(fetchSpy).toHaveBeenCalledTimes(1);
      expect(fetchSpy).toHaveBeenCalledWith("http://localhost/media/serif.woff2");
      expect(svg).toContain('font-family: "Plate Serif"');
      expect(svg).toMatch(/url\("data:font\/woff2;base64,[^"]+"\)/);
      expect(svg).not.toContain("unused.woff2");
      expect(svg).not.toContain("/media/serif.woff2");
    });

    it("embeds only the font subsets that cover the diagram's text", async () => {
      const element = sizedElement();
      element.textContent = "Included: 41 ↓";
      useFakeComputedStyle('"Plate Serif", Georgia, serif');
      stubStyleSheet([
        fontFaceRule("Plate Serif", "latin.woff2", "U+0000-00FF, U+2190-2193"),
        fontFaceRule("Plate Serif", "wildcard.woff2", "U+2??"),
        fontFaceRule("Plate Serif", "cyrillic.woff2", "U+0400-045F, U+0490-0491"),
        fontFaceRule("Plate Serif", "greek.woff2", "U+0370-03FF"),
      ]);
      const fetchSpy = stubFontFetch();

      await downloadElementAsPng(element, "prisma-flow-diagram.png");

      const fetched = fetchSpy.mock.calls.map(([url]) => String(url));
      expect(fetched.sort()).toEqual(["http://localhost/media/latin.woff2"]);
    });

    it("keeps the bullet glyph's subset, since list markers are not in the text", async () => {
      const element = sizedElement();
      element.textContent = "Wrong population 31";
      useFakeComputedStyle('"Plate Serif", Georgia, serif');
      stubStyleSheet([fontFaceRule("Plate Serif", "punctuation.woff2", "U+2000-206F")]);
      const fetchSpy = stubFontFetch();

      await downloadElementAsPng(element, "prisma-flow-diagram.png");

      expect(fetchSpy).toHaveBeenCalledWith("http://localhost/media/punctuation.woff2");
    });

    it("still exports, falling back to the next font, when a font file cannot be fetched", async () => {
      const element = sizedElement();
      useFakeComputedStyle('"Missing Serif", Georgia, serif');
      stubStyleSheet([fontFaceRule("Missing Serif", "gone.woff2")]);
      vi.stubGlobal(
        "fetch",
        vi.fn(async () => ({ ok: false }))
      );

      await downloadElementAsPng(element, "prisma-flow-diagram.png");

      expect(clickSpy).toHaveBeenCalledTimes(1);
      expect(exportedSvg()).not.toContain("@font-face");
    });
  });
});

describe("LIGHT_TOKENS", () => {
  it("matches the light :root palette in globals.css", () => {
    const css = readFileSync(path.resolve(__dirname, "../app/globals.css"), "utf8");
    const root = css.match(/:root\s*\{([^}]*)\}/)?.[1] ?? "";
    const declared = Object.fromEntries(
      [...root.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)].map(([, name, value]) => [
        name,
        value.trim(),
      ])
    );

    for (const [name, value] of Object.entries(LIGHT_TOKENS)) {
      expect(declared[name], name).toBe(value);
    }
  });
});
