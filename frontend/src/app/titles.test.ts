import { describe, expect, it, vi } from "vitest";

import { metadata as root } from "./layout";
import { metadata as account } from "./account/layout";
import { metadata as invitation } from "./invitations/[token]/layout";
import { metadata as login } from "./login/layout";
import { metadata as register } from "./register/layout";
import { metadata as citations } from "./review-projects/[id]/citations/layout";
import { metadata as conflicts } from "./review-projects/[id]/conflicts/layout";
import { metadata as criteria } from "./review-projects/[id]/criteria/layout";
import { metadata as duplicates } from "./review-projects/[id]/duplicates/layout";
import { metadata as extractionFields } from "./review-projects/[id]/extraction-fields/layout";
import { metadata as flowDiagram } from "./review-projects/[id]/flow-diagram/layout";
import { metadata as projectInvitations } from "./review-projects/[id]/invitations/layout";
import { metadata as searchTerms } from "./review-projects/[id]/search-terms/layout";

// The root layout loads its fonts at import time, which only works inside Next's build.
vi.mock("next/font/google", () => {
  const font = () => ({ variable: "font" });
  return { Source_Serif_4: font, IBM_Plex_Sans: font, IBM_Plex_Mono: font };
});

// #108: only the root layout had a title, so every tab and history entry read the same.
describe("route titles", () => {
  it("gives the root a default and a suffix template for every route", () => {
    expect(root.title).toEqual({
      default: "Automatic Systematic Review",
      template: "%s · Automatic Systematic Review",
    });
  });

  it.each([
    ["login", login, "Log in"],
    ["register", register, "Register"],
    ["account", account, "Account and billing"],
    ["invitation", invitation, "Join a review"],
    ["criteria", criteria, "Criteria"],
    ["search terms", searchTerms, "Search terms"],
    ["citations", citations, "Citations"],
    ["duplicates", duplicates, "Possible duplicates"],
    ["conflicts", conflicts, "Conflicts"],
    ["extraction fields", extractionFields, "Extraction fields"],
    ["PRISMA flow", flowDiagram, "PRISMA flow"],
    ["project invitations", projectInvitations, "Invitations"],
  ])("names the %s page", (_name, metadata, title) => {
    expect(metadata.title).toBe(title);
  });
});
