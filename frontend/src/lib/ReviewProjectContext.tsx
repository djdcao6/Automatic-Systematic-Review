"use client";

import { createContext, useContext, type ReactNode } from "react";

import type { ReviewProjectDetail } from "@/lib/api";

export type ReviewProjectContextValue = {
  project: ReviewProjectDetail;
  isOwner: boolean;
  refreshProject: () => Promise<void>;
};

const ReviewProjectContext = createContext<ReviewProjectContextValue | null>(null);

export function ReviewProjectProvider({
  value,
  children,
}: {
  value: ReviewProjectContextValue;
  children: ReactNode;
}) {
  return <ReviewProjectContext.Provider value={value}>{children}</ReviewProjectContext.Provider>;
}

export function useReviewProject(): ReviewProjectContextValue {
  const value = useContext(ReviewProjectContext);
  if (!value) {
    throw new Error("useReviewProject must be used inside a ProjectShell");
  }
  return value;
}
