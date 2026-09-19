// The export is drawn from an SVG <foreignObject>. An SVG loaded as an image is
// isolated from the page, so it sees none of the page's stylesheets, custom
// properties or web fonts. Everything the picture needs is therefore copied
// into the markup first: computed styles inline on every node, and the used
// @font-face rules as data URIs.

// The light palette from DESIGN.md, so the PNG reads the same whatever theme
// the viewer is in. Mirrors the light `:root` in globals.css; png-export.test.ts
// fails if the two drift apart.
export const LIGHT_TOKENS = {
  "--background": "#f4f5f7",
  "--surface": "#ffffff",
  "--text": "#151a23",
  "--text-muted": "#566070",
  "--border": "#d9dee6",
  "--primary": "#1b2230",
  "--primary-hover": "#2a3446",
  "--on-primary": "#ffffff",
  "--accent": "#2456d6",
  "--include": "#1e6f55",
  "--exclude": "#9b2c3a",
  "--maybe": "#8a5f08",
  "--ai-suggestion": "#646a78",
  "--wash": "rgba(138, 95, 8, 0.16)",
  "--shadow-frame": "0 6px 18px -10px rgba(21, 26, 35, 0.25)",
} as const;

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("Failed to load the diagram as an image"));
    image.src = src;
  });
}

function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error("Failed to read a font file"));
    reader.readAsDataURL(blob);
  });
}

function unquote(value: string): string {
  return value.trim().replace(/^(["'])(.*)\1$/, "$2");
}

// Used heights are a result of layout, not an input to it. Pinned onto a table
// row or cell they add the collapsed border a second time, so every row grows.
// Content sets the height again in the export, from the same widths and fonts.
const LAYOUT_RESULT_PROPERTIES = new Set(["height", "block-size"]);

/**
 * Copy every computed style onto a matching clone of each node. Computed values
 * are fully resolved (no var(), no relative units), and include inherited
 * properties, so the isolated SVG needs nothing from the page.
 */
function inlineComputedStyles(source: Element, target: Element, families: Set<string>): void {
  const computed = window.getComputedStyle(source);
  let declarations = "";
  for (let index = 0; index < computed.length; index += 1) {
    const name = computed[index];
    if (name.startsWith("--") || LAYOUT_RESULT_PROPERTIES.has(name)) continue;
    declarations += `${name}:${computed.getPropertyValue(name)};`;
  }
  target.setAttribute("style", declarations);

  for (const family of computed.getPropertyValue("font-family").split(",")) {
    families.add(unquote(family));
  }

  for (let index = 0; index < source.children.length; index += 1) {
    inlineComputedStyles(source.children[index], target.children[index], families);
  }
}

/**
 * Clone the element with resolved styles, computed as if the page were in its
 * light theme. The light tokens are set on the live element for the duration of
 * one synchronous read and then removed, so nothing repaints in between.
 */
function cloneWithLightStyles(element: HTMLElement): { clone: HTMLElement; families: Set<string> } {
  const clone = element.cloneNode(true) as HTMLElement;
  const families = new Set<string>();
  const previousStyle = element.getAttribute("style");

  for (const [name, value] of Object.entries(LIGHT_TOKENS)) {
    element.style.setProperty(name, value);
  }
  // `color` is inherited from the body, where it was already resolved in the
  // viewer's theme, so the overridden tokens never reach it.
  element.style.setProperty("color", LIGHT_TOKENS["--text"]);

  try {
    inlineComputedStyles(element, clone, families);
  } finally {
    if (previousStyle === null) {
      element.removeAttribute("style");
    } else {
      element.setAttribute("style", previousStyle);
    }
  }

  // The plate's margin and drop shadow belong to the page, not the picture.
  clone.style.setProperty("margin", "0");
  clone.style.setProperty("box-shadow", "none");
  return { clone, families };
}

const fontDataUrls = new Map<string, Promise<string | null>>();

function fetchFontDataUrl(url: string): Promise<string | null> {
  let pending = fontDataUrls.get(url);
  if (!pending) {
    pending = fetch(url)
      .then((response) => (response.ok ? response.blob() : Promise.reject(new Error(url))))
      .then(blobToDataUrl)
      .catch(() => null);
    fontDataUrls.set(url, pending);
  }
  return pending;
}

/** Whether a `unicode-range` descriptor covers any of the code points. */
function coversAnyCodePoint(unicodeRange: string, codePoints: Set<number>): boolean {
  const ranges = [...unicodeRange.matchAll(/U\+([0-9a-f?]+)(?:-([0-9a-f]+))?/gi)];
  if (ranges.length === 0) return true; // no descriptor: covers everything
  return ranges.some(([, start, end]) => {
    const low = parseInt(start.replace(/\?/g, "0"), 16);
    const high = end ? parseInt(end, 16) : parseInt(start.replace(/\?/g, "f"), 16);
    return [...codePoints].some((codePoint) => codePoint >= low && codePoint <= high);
  });
}

/**
 * The page's @font-face rules for the given families, with each font file
 * inlined as a data URI. Fonts arrive split by script (Latin, Cyrillic, ...);
 * only the faces that cover a character in `text` are embedded, which keeps the
 * image small. A face whose file cannot be fetched is left out, so that text
 * falls back to the next family in its stack (Georgia, system-ui).
 */
async function embeddedFontFaces(families: Set<string>, text: string): Promise<string> {
  // List bullets are drawn by the browser and are not in the text content.
  const codePoints = new Set([0x2022, ...Array.from(text, (char) => char.codePointAt(0)!)]);
  const faces: Promise<string>[] = [];

  for (const sheet of Array.from(document.styleSheets)) {
    let rules: CSSRule[];
    try {
      rules = Array.from(sheet.cssRules);
    } catch {
      continue; // a cross-origin stylesheet cannot be read
    }

    for (const rule of rules) {
      if (!rule.cssText.startsWith("@font-face")) continue;
      const { style } = rule as CSSFontFaceRule;
      if (!families.has(unquote(style.getPropertyValue("font-family")))) continue;
      if (!coversAnyCodePoint(style.getPropertyValue("unicode-range"), codePoints)) continue;

      const base = sheet.href ?? document.baseURI;
      const urls = [...rule.cssText.matchAll(/url\(\s*(["']?)(.*?)\1\s*\)/g)];
      faces.push(
        (async () => {
          let cssText = rule.cssText;
          for (const [reference, , path] of urls) {
            const dataUrl = await fetchFontDataUrl(new URL(path, base).href);
            if (!dataUrl) return "";
            cssText = cssText.replace(reference, `url("${dataUrl}")`);
          }
          return cssText;
        })()
      );
    }
  }

  return (await Promise.all(faces)).join("\n");
}

async function elementToPngBlob(element: HTMLElement): Promise<Blob> {
  const rect = element.getBoundingClientRect();
  // Whole pixels: a canvas truncates fractions, which would clip the last border.
  const width = Math.ceil(rect.width || element.scrollWidth || 1);
  const height = Math.ceil(rect.height || element.scrollHeight || 1);

  // The web fonts must be decoded before their metrics are read below.
  await document.fonts?.ready;

  const { clone, families } = cloneWithLightStyles(element);
  const markup = new XMLSerializer().serializeToString(clone);
  const fontFaces = await embeddedFontFaces(families, element.textContent ?? "");
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}"><style><![CDATA[${fontFaces}]]></style><foreignObject width="100%" height="100%"><div xmlns="http://www.w3.org/1999/xhtml">${markup}</div></foreignObject></svg>`;
  // A data: URL, not a blob: URL. Chrome taints the canvas of a blob: SVG that
  // holds a foreignObject, and a tainted canvas cannot be exported.
  const image = await loadImage(`data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`);

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) {
    throw new Error("Canvas 2D context is not available");
  }
  // Opaque ground, so the PNG never depends on the viewer's background.
  context.fillStyle = LIGHT_TOKENS["--background"];
  context.fillRect(0, 0, width, height);
  context.drawImage(image, 0, 0, width, height);

  return await new Promise<Blob>((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) {
        resolve(blob);
      } else {
        reject(new Error("Failed to rasterize the diagram as a PNG"));
      }
    }, "image/png");
  });
}

export async function downloadElementAsPng(element: HTMLElement, filename: string): Promise<void> {
  const blob = await elementToPngBlob(element);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
