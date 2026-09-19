"use client";

import Link from "next/link";
import { useSelectedLayoutSegment } from "next/navigation";
import { useId, useRef, useState, type KeyboardEvent } from "react";

import type { ReviewMode } from "@/lib/api";

type Viewer = { reviewMode: ReviewMode; isOwner: boolean };
type RailItem = { segment: string; label: string; visible?: (viewer: Viewer) => boolean };

const ITEMS: RailItem[] = [
  { segment: "criteria", label: "Criteria" },
  { segment: "search-terms", label: "Search terms" },
  { segment: "citations", label: "Citations" },
  { segment: "duplicates", label: "Duplicates" },
  { segment: "conflicts", label: "Conflicts", visible: ({ reviewMode }) => reviewMode === "dual" },
  { segment: "extraction-fields", label: "Extraction fields" },
  { segment: "flow-diagram", label: "PRISMA flow" },
  {
    segment: "invitations",
    label: "Invitations",
    visible: ({ reviewMode, isOwner }) => reviewMode === "dual" && isOwner,
  },
];

export function ProjectRail({
  reviewProjectId,
  reviewMode,
  isOwner,
}: {
  reviewProjectId: string;
  reviewMode: ReviewMode;
  isOwner: boolean;
}) {
  const currentSegment = useSelectedLayoutSegment();
  const navId = useId();
  const [open, setOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape" && open) {
      setOpen(false);
      menuButton.current?.focus();
    }
  }

  return (
    <div className="rail" data-open={open} onKeyDown={handleKeyDown}>
      <button
        ref={menuButton}
        type="button"
        className="rail-menu"
        aria-expanded={open}
        aria-controls={navId}
        onClick={() => setOpen((wasOpen) => !wasOpen)}
      >
        Menu
      </button>
      <nav id={navId} aria-label="Project">
        <ul>
          {ITEMS.filter((item) => !item.visible || item.visible({ reviewMode, isOwner })).map(
            (item) => (
              <li key={item.segment}>
                <Link
                  href={`/review-projects/${reviewProjectId}/${item.segment}`}
                  aria-current={item.segment === currentSegment ? "page" : undefined}
                  onClick={() => setOpen(false)}
                >
                  {item.label}
                </Link>
              </li>
            )
          )}
        </ul>
      </nav>
    </div>
  );
}
