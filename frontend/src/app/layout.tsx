import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans, Source_Serif_4 } from "next/font/google";
import Link from "next/link";
import "./globals.css";

import { LogoutButton } from "@/components/LogoutButton";

// Reading and display voice. The optical-size axis lets titles and abstracts
// share one family: the browser picks the cut from the rendered size.
const sourceSerif = Source_Serif_4({
  variable: "--font-source-serif",
  subsets: ["latin"],
  axes: ["opsz"],
});

// UI voice: labels, tables, forms, buttons.
const plexSans = IBM_Plex_Sans({
  variable: "--font-plex-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

// Identifiers: DOIs, IDs, queries, keycaps.
const plexMono = IBM_Plex_Mono({
  variable: "--font-plex-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "Automatic Systematic Review",
  description:
    "Screen citations against your criteria, extract data from full texts, and keep your decisions separate from the AI's suggestions.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${sourceSerif.variable} ${plexSans.variable} ${plexMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
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
