import { PageStatus } from "@/components/PageStatus";

// What a section page shows when its link is hidden for this project or role
// but the Reviewer reached it anyway, for example from an old bookmark.
export function SectionUnavailable() {
  return <PageStatus error="This section isn't available for this project." />;
}
