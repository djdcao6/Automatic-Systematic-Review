import type { Metadata } from "next";
import Link from "next/link";

// Fonts are npm packages so a build never downloads from Google Fonts, whose
// outages failed CI builds. Each file declares every script subset (Latin
// extended, Greek, Cyrillic, Vietnamese) behind unicode-range, so a Greek
// letter or a Czech author name loads its subset instead of falling back.
// Reading and display voice. The optical-size axis lets titles and abstracts
// share one family: the browser picks the cut from the rendered size.
import "@fontsource-variable/source-serif-4/opsz.css";
// UI voice: labels, tables, forms, buttons.
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
// Identifiers: DOIs, IDs, queries, keycaps.
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "./globals.css";

import { LogoutButton } from "@/components/LogoutButton";
import { SkipLink } from "@/components/SkipLink";

export const metadata: Metadata = {
  // Routes add their own name through `layout.tsx` metadata; this is the fallback and suffix.
  title: {
    default: "Automatic Systematic Review",
    template: "%s · Automatic Systematic Review",
  },
  description:
    "Screen citations against your criteria, extract data from full texts, and keep your decisions separate from the AI's suggestions.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col">
        <SkipLink />
        <div className="topbar">
          <div className="topbar-inner">
            <Link href="/" className="brand">
              Automatic Systematic Review
            </Link>
            <LogoutButton />
          </div>
        </div>
        <div className="frame">{children}</div>
      </body>
    </html>
  );
}
