"use client";

import Link from "next/link";
import { useRef } from "react";

import { useScreeningShortcuts } from "@/lib/useScreeningShortcuts";

const numbers = new Intl.NumberFormat("en-US");

function NeighbourLink({
  href,
  label,
  shortcut,
  innerRef,
}: {
  href: string | null;
  label: string;
  shortcut: string;
  innerRef: React.Ref<HTMLAnchorElement>;
}) {
  const content = (
    <>
      {label}
      <kbd aria-hidden="true">{shortcut.toUpperCase()}</kbd>
    </>
  );

  if (!href) {
    return (
      <span className="folio-link" aria-disabled="true">
        {content}
      </span>
    );
  }
  return (
    <Link href={href} className="folio-link" aria-keyshortcuts={shortcut} ref={innerRef}>
      {content}
    </Link>
  );
}

// The strip above the reading page: where this citation sits in the list, how
// much of the list has a decision, and the way to the neighbouring citations.
export function ScreeningFolio({
  position,
  total,
  decided,
  modeNote,
  previousHref,
  nextHref,
}: {
  position: number;
  total: number;
  decided: number;
  modeNote: string;
  previousHref: string | null;
  nextHref: string | null;
}) {
  const previousRef = useRef<HTMLAnchorElement>(null);
  const nextRef = useRef<HTMLAnchorElement>(null);
  useScreeningShortcuts({
    k: () => previousRef.current?.click(),
    j: () => nextRef.current?.click(),
  });

  return (
    <header className="folio">
      <div className="folio-row">
        <p className="label">Title and abstract screening</p>
        <nav className="folio-nav" aria-label="Citations">
          <NeighbourLink href={previousHref} label="Previous" shortcut="k" innerRef={previousRef} />
          <NeighbourLink href={nextHref} label="Next" shortcut="j" innerRef={nextRef} />
        </nav>
      </div>
      <p className="folio-count">
        <span>{numbers.format(position)}</span>{" "}
        <span className="of">of {numbers.format(total)}</span>
      </p>
      <p className="folio-mode">{modeNote}</p>
      <div
        className="progress"
        role="progressbar"
        aria-label="Screening progress"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={decided}
        aria-valuetext={`${numbers.format(decided)} of ${numbers.format(total)} decided`}
      >
        <span style={{ width: `${total > 0 ? (decided / total) * 100 : 0}%` }} />
      </div>
    </header>
  );
}
