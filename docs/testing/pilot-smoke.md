# Pilot smoke protocol

A short, repeatable manual run that proves a **deployed** revision of the app works for two
Reviewers before a pilot release goes out. Issue #93, part of the pilot gate (#53, roadmap #88).
The run supplies the smoke evidence #65 needs. It is manual on purpose: #94 automates it later, and
the step IDs below (A1, B7, C9, ...) are the test-case names #94 should reuse.

The expected values were checked on 2026-09-21, at `cec2609`, by replaying this protocol's data
against the backend code with the fixtures in `docs/testing/pilot-smoke/` and the AI calls stubbed.
That replay was a throwaway test and is not kept. Re-check the values if the CSV export, the PRISMA
counts or the Conflict rules change.

## Ground rules

- **Synthetic data only.** Use the fixtures here. Never upload real Citations, patient data or a
  real Full Text. The app sends abstracts, Criteria and Full Text to Anthropic's API (AI disclosure,
  #61).
- **Do not delete, reset or edit existing pilot data** to run this. Make new projects named
  `Smoke Solo <date>` and `Smoke Dual <date>`. Leave them in place afterwards; removing them is a
  separate operator decision, not a step here.
- **Real provider.** A deployed host has no AI stub, so every AI Suggestion here comes from the real
  model. Its wording changes between runs, so AI cells are checked for shape, never for exact text.
  Stubbed checks live in CI and are not part of this record.
- **Bounded cost.** At most 9 model calls: 3 screening suggestions in each project (the missing-abstract
  Citation makes none) and 3 Full-Text Suggestions. Read the Anthropic Console usage before the run
  and after it, and record the difference (step G2).
- **Two separate browser sessions.** The sign-in token lives in `localStorage`, so two normal windows
  of one profile share one Reviewer. Use two browser profiles, or one normal window plus one private
  window. Call them **Session A** (Owner) and **Session B** (Co-Reviewer).
- **Keep secrets out of the evidence.** Blur emails, tokens, invitation links and passwords in
  screenshots and logs. Do not attach the PDFs' contents beyond the fixtures.
- **Stop on a blocker.** If a step fails in a way that stops the next one, mark it FAIL, note why,
  and continue with the steps that still make sense. A failed run means the release is on hold.

## Before you start

| What | Detail |
|---|---|
| Revision | The commit you intend to release. `git rev-parse origin/main` (or the release branch). |
| Host | `asr-api` and `asr-web` deployed (see `docs/deploy/render.md`). No deploy in progress. |
| Allowlist | `SIGNUP_ALLOWLIST` contains **Reviewer A**'s email and does **not** contain Reviewer B's. |
| Reviewer A | An email you control, on the allowlist. The Owner in both projects. |
| Reviewer B | A different email you control, **not** on the allowlist. The app sends no mail, so any address works; use one you control so no stranger gets an account. |
| Unlisted address | `not-on-list@example.com` or similar. It is only ever rejected, so nothing is stored. |
| Provider | The operator has approved using the real provider for about 9 model calls on synthetic data, and the Anthropic Console monthly cap is set (`docs/deploy/render.md`, "Before you start"). Note the Console usage figure now; G2 compares it. |
| Passwords | At least 8 characters. Keep them in a password manager, not in the result. |
| Fixtures | The five files in `docs/testing/pilot-smoke/`, on the machine running the browsers. |
| Tools | Browser DevTools (Network tab), a text editor to read CSV, an image viewer, a PDF viewer. |

**Re-running.** Reviewers A and B already exist, and the first run's projects stay in place, so:
skip A3 and A5 (mark `SKIP re-run`), log in as A at A6, and mark A7 `SKIP re-run` (the list is no
longer empty; B3, C2 and C3 still test empty states on the new projects). A4 still runs. Name the new
projects with the new date, and add `-2` if you run twice in a day. In C5 open the new invitation link
and use **Log in & Join** instead of **Register & Join**.

## Fixtures

Import files (columns `title, abstract, authors, year, source, doi`):

| File | Rows |
|---|---|
| `import-1-pubmed.csv` | S1, S2, S3, S4, all `PubMed` |
| `import-2-embase.csv` | S1 again (same DOI, same title, no abstract/authors/year), `Embase` |

PDFs, one page each, invented text, text layer checked with the app's own parser:

| File | For | Shows |
|---|---|---|
| `study-1-v1.pdf` | S1, first upload | `VERSION 1 (DRAFT)`, "enrolled 40 adult participants" |
| `study-1-v2.pdf` | S1, replacement | `VERSION 2 (CORRECTED)`, "enrolled 48 adult participants" |
| `study-3.pdf` | S3 | "enrolled 30 children aged 4 to 10" |

The four Citations:

| | Title | What it exercises |
|---|---|---|
| S1 | Synthetic Study One: Saline Nasal Rinse for Adult Colds | Duplicate across two imports; included with a text-layer PDF; PDF replacement |
| S2 | Synthetic Study Two: Saline Spray in Adults | A Conflict in the Dual project |
| S3 | Synthetic Study Three: Saline Rinse in Children | Full-Text exclusion with an allowed reason |
| S4 | Synthetic Study Four: Nasal Rinse Without Abstract | Missing abstract, so no AI Suggestion |

Criteria for both projects (save before the first decision, they lock after it):

| Field | Value |
|---|---|
| Population | `Adults with a synthetic cold` |
| Intervention | `Saline nasal rinse` |
| Comparison | `No rinse` |
| Outcome | `Symptom score` |
| Exclusion rules (one per line) | `Wrong population` and `Wrong study design` |
| Notes | `Synthetic smoke-test data only` |

## Expected results

Decisions to record (reasons are typed exactly as shown; blank means leave the field empty):

| | Solo project | Dual: Owner | Dual: Co-Reviewer | Dual: final |
|---|---|---|---|---|
| S1 | include | include | include | include |
| S2 | include | include, `Adults, relevant` | exclude, `Spray, not rinse` | Conflict, Owner resolves to exclude, `Spray is not a rinse` |
| S3 | include | include | include | include |
| S4 | exclude, `No abstract to assess` | exclude, `No abstract to assess` | exclude, `No abstract to assess` | exclude |
| Full-Text (S1) | | include | | include, Sample size `48` |
| Full-Text (S3) | | exclude, `Wrong population` | | exclude, `Wrong population` |

### PRISMA counts (EXP-FLOW-*)

Read from the PRISMA flow page and its Numeric Summary table. "Pending" is
"N citation(s) still pending a Screening Decision". "FT" means Full-Text: "FT assessed", "FT excluded"
and "FT pending" (`N citation(s) still pending a Full-Text Decision`) are the Full-Text counts.

| Checkpoint | PubMed | Embase | Total identified | Duplicates removed | Screened | Excluded | Pending | FT assessed | FT excluded | Included | FT pending |
|---|---|---|---|---|---|---|---|---|---|---|---|
| EXP-FLOW-IMPORT (either project, after both imports) | 4 | 1 | 5 | 1 | 0 | 0 | 4 | 0 | 0 | 0 | 0 |
| EXP-FLOW-SOLO (Solo, all decided) | 4 | 1 | 5 | 1 | 4 | 1 | 0 | 0 | 0 | 0 | 3 |
| EXP-FLOW-OWNER-ONLY (Dual, Owner decided S1, S2, S4, Co-Reviewer none) | 4 | 1 | 5 | 1 | 0 | 0 | 4 | 0 | 0 | 0 | 0 |
| EXP-FLOW-CONFLICT (Dual, both decided, Conflict unresolved) | 4 | 1 | 5 | 1 | 3 | 1 | 1 | 0 | 0 | 0 | 2 |
| EXP-FLOW-FINAL (Dual, everything done) | 4 | 1 | 5 | 1 | 4 | 2 | 0 | 2 | 1 (`Wrong population: 1`) | 1 | 0 |

EXP-FLOW-OWNER-ONLY is the blinding check: while only one Reviewer has decided, the counts must not
move, or the other Reviewer could read the first one's decisions off them.

### CSV (EXP-CSV-*)

The file starts with a `# `-prefixed Criteria block, then a blank line, then the header row. A
spreadsheet shows it as odd first rows; read it in a text editor, or skip the first 8 lines.

```
# Review Project Criteria
# Population: Adults with a synthetic cold
# Intervention: Saline nasal rinse
# Comparison: No rinse
# Outcome: Symptom score
# Exclusion Rules: Wrong population; Wrong study design
# Notes: Synthetic smoke-test data only

```

Compare every cell exactly, except the two AI columns. **AI cells:** `ai_suggestion_decision` is one
of `include`, `exclude`, `maybe` and `ai_suggestion_reason` is non-empty for S1, S2 and S3; both are
`not_available` for S4. Write `<AI>` below for those cells. Rows are in import order. The download is
named `citations.csv` for every Review Project; a second export in the same browser lands as
`citations (1).csv`, `citations (2).csv` and so on, which is the browser de-duplicating, not the app.
Track which file is which by export order, not by name.

**EXP-CSV-SOLO** (11 columns)

```
title,abstract,authors,year,source,screening_decision,reason,ai_suggestion_decision,ai_suggestion_reason,full_text_decision,full_text_reason
Synthetic Study One: Saline Nasal Rinse for Adult Colds,A synthetic randomized trial of saline nasal rinse in adults with a cold. Symptom scores fell more in the rinse group.,"Alpha, A.; Beta, B.",2020,PubMed; Embase,include,,<AI>,<AI>,,
Synthetic Study Two: Saline Spray in Adults,A synthetic cohort of adults using a saline spray. Symptom scores were similar between groups.,"Gamma, C.",2019,PubMed,include,,<AI>,<AI>,,
Synthetic Study Three: Saline Rinse in Children,A synthetic trial of saline nasal rinse in children with a cold. Symptom scores fell in the rinse group.,"Delta, D.; Epsilon, E.",2021,PubMed,include,,<AI>,<AI>,,
Synthetic Study Four: Nasal Rinse Without Abstract,,"Zeta, Z.",2018,PubMed,exclude,No abstract to assess,not_available,not_available,,
```

**EXP-CSV-DUAL-FINAL** (14 columns: the 11 above, then `owner_decision`, `co_reviewer_decision`,
and one column per active Extraction Field, here `Sample size`)

```
title,abstract,authors,year,source,screening_decision,reason,ai_suggestion_decision,ai_suggestion_reason,full_text_decision,full_text_reason,owner_decision,co_reviewer_decision,Sample size
Synthetic Study One: Saline Nasal Rinse for Adult Colds,A synthetic randomized trial of saline nasal rinse in adults with a cold. Symptom scores fell more in the rinse group.,"Alpha, A.; Beta, B.",2020,PubMed; Embase,include,,<AI>,<AI>,include,,include,include,48
Synthetic Study Two: Saline Spray in Adults,A synthetic cohort of adults using a saline spray. Symptom scores were similar between groups.,"Gamma, C.",2019,PubMed,exclude,Spray is not a rinse,<AI>,<AI>,,,include,exclude,
Synthetic Study Three: Saline Rinse in Children,A synthetic trial of saline nasal rinse in children with a cold. Symptom scores fell in the rinse group.,"Delta, D.; Epsilon, E.",2021,PubMed,include,,<AI>,<AI>,exclude,Wrong population,include,include,
Synthetic Study Four: Nasal Rinse Without Abstract,,"Zeta, Z.",2018,PubMed,exclude,No abstract to assess,not_available,not_available,,,exclude,exclude,
```

**EXP-CSV-DUAL-BLIND** (Session B, before B has decided anything): the same four title/abstract/authors/
year/source cells, and **every** cell from `screening_decision` through `co_reviewer_decision` empty
on all four rows.

**EXP-CSV-DUAL-REVEAL** (Session B, after B decided only S1): S1's row shows `include`, the AI cells,
`owner_decision` `include` and `co_reviewer_decision` `include`. S2, S3 and S4 stay as in EXP-CSV-DUAL-BLIND.

## Steps

Each step has a Result column. Copy this whole section into the result comment and fill it in with
`PASS`, `FAIL` or `SKIP`, plus a note for anything but a plain PASS.

### A. Revision, access and consent

| ID | Do | Expect | Result |
|---|---|---|---|
| A0 | **Before anything else**, open the Anthropic Console's usage page and write down the current figure. G2 subtracts this from the figure at the end, and it cannot be reconstructed afterwards. | A number recorded here, not a promise to check later. | |
| A1 | Open `https://<api>/health`. | `{"status": "ok"}`. | |
| A2 | Record the deployed commit of `asr-api` and of `asr-web` from the Render dashboard (each service's latest deploy). Record the date, the browser and version, and the intended release commit. Note whether the `asr-api` deploy log shows `alembic upgrade head` succeeding. | Both deployed commits equal the intended commit. The app has no version page, so the dashboard is the only evidence; if the two differ, the run tests a mixed deploy and is FAIL. | |
| A3 | Register page, an **allowlisted** email (Reviewer A), consent box **unticked**, submit. | `Accept the AI disclosure to create an account.` No account created. The box's text reads "I understand: Abstracts, PDFs and criteria you add are sent to Anthropic's API to generate suggestions. Don't upload patient-identifiable data." | |
| A4 | Register with the **unlisted** address, consent ticked. | `Sign-up is invite only during the pilot. Ask to be added, or accept an invitation from a Review Project's owner.` | |
| A5 | Register Reviewer A, consent ticked. | Redirected to the log-in page. | |
| A6 | Log in as A with a wrong password, then the right one. | First: `Incorrect email or password`. Second: the Review Projects page. | |
| A7 | On the Review Projects page as A. | Genuine empty state: `No review projects yet. Create one above.` | |

### B. Solo review (Session A)

| ID | Do | Expect | Result |
|---|---|---|---|
| B1 | Create `Smoke Solo <date>`, Merge Mode **Combine**, Review Mode **Solo**. Open it. In DevTools > Network, look at the `GET /me` response. | The project opens with no "Before you continue" consent dialog; header shows `Review Mode: solo`. No Conflicts item in the side rail. `GET /me` shows a non-null `ai_consent_at`, so the server recorded the consent given at sign-up. | |
| B2 | Criteria: enter the Criteria table above, **Save Criteria**. | Saved; values still there after a reload. | |
| B3 | Citations page, before any import. | Genuine empty state: `No citations yet. Upload a RIS or CSV file above.` | |
| B4 | Upload `import-1-pubmed.csv`. | Four Citations listed (S1 to S4). S4 is marked `(needs abstract)`. No skipped-rows notice. | |
| B5 | Upload `import-2-embase.csv`. Then open Duplicates and PRISMA flow. | Still four Citations, no fifth. Duplicates: nothing listed once the page has loaded (`No outstanding Possible Duplicates.`; that panel also shows this text while still loading, so reload once and check it stays). Flow matches **EXP-FLOW-IMPORT**. | |
| B6 | Open S1. Do not touch the form yet. | Abstract shown. No decision is selected. The margin box "AI suggestion (advisory)" shows `Preparing an AI suggestion…`, then `<decision>: <reason>`. The suggestion has **not** filled the decision or the reason. Note the AI's decision. | |
| B7 | Click **Save Decision** with nothing chosen. | `Choose Include, Exclude or Maybe first.` Nothing saved. | |
| B8 | Failed then retried save. Choose **include**. In DevTools > Network set throttling to **Offline**. Click **Save Decision**. Set it back to **No throttling**. Reload the page. | Offline: `Failed to save screening decision.` and **no** `Decision saved.` line. After the reload the decision is **not** selected (nothing was recorded). | |
| B9 | Choose **include** again and **Save Decision**. | `Decision saved.` A reload shows include selected. | |
| B10 | S2: open, choose **include**, save. S3: same. | Each shows its AI suggestion in the margin, separate from the choice, and `Decision saved.` Note whether the AI agreed. | |
| B11 | S4: open. Choose **exclude**, reason `No abstract to assess`, save. | Flag `No abstract`. Margin: `This citation is missing an abstract, so no AI Suggestion could be generated.` (unavailable state, no model call). `Decision saved.` | |
| B12 | PRISMA flow page. | Matches **EXP-FLOW-SOLO**, in both the diagram and the Numeric Summary table. | |
| B13 | **Export CSV** (project header). | Matches **EXP-CSV-SOLO**. AI cells sit in their own columns, apart from `screening_decision`. | |

### C. Dual review (Sessions A and B)

| ID | Do | Expect | Result |
|---|---|---|---|
| C1 | Session A: create `Smoke Dual <date>`, Combine, **Dual**. Repeat B2, B4 and B5 exactly. | Same results as B2, B4, B5. Flow matches **EXP-FLOW-IMPORT**. Side rail has a Conflicts item. | |
| C2 | Session A: Conflicts page. | Genuine empty state: `No outstanding Conflicts.` | |
| C3 | Session A: Extraction fields page. | Genuine empty state: `No extraction fields yet. Add one below.` Then add Name `Sample size`, Description `Number of participants enrolled` with **Add Field**; it appears in the list. | |
| C4 | Session A: Invitations, **Generate Invite Link**. | A link appears. Copy it. | |
| C5 | Session B: open the link. Enter Reviewer B's email and a password, tick consent, **Register & Join** (re-run: **Log in & Join**). | Lands in `Smoke Dual <date>` with no "Before you continue" dialog (the consent box at registration was enough). Reviewer B was never on the allowlist; the invitation is what admitted them. | |
| C6 | Session B: go to the Review Projects page, fill the create form with any name, Merge Mode and Review Mode, and submit. | `Your account can work in the Review Project that invited you, but creating Review Projects is invite only during the pilot.` | |
| C7 | Session A: record the Owner column of the decisions table for **S1, S2 and S4**. Leave S3 undecided for now. | Each `Decision saved.` Flow matches **EXP-FLOW-OWNER-ONLY**. | |
| C8 | Session B: open S1 without deciding. | Margin AI box: `Hidden until you record your own Screening Decision.` Owner's Decision box: `Sealed until you record your own Screening Decision.` No AI text and no Owner decision anywhere on the page. | |
| C9 | Session B: PRISMA flow, then **Export CSV**. | Flow matches **EXP-FLOW-OWNER-ONLY** (does not reveal the Owner's decisions). CSV matches **EXP-CSV-DUAL-BLIND**. | |
| C10 | Session B: record **include** on S1 only, then **Export CSV** again. | S1 reveals the Owner's decision (`include`) and the AI Suggestion. CSV matches **EXP-CSV-DUAL-REVEAL**: blinding is per Citation. | |
| C11 | Blinding for the Owner too. Session B: record **include** on S3. Session A: open S3 **without deciding**, then record **include**. | Before deciding, Session A sees the mirror of C8: AI box `Hidden until you record your own Screening Decision.` and Co-Reviewer's Decision box `Sealed until you record your own Screening Decision.` After saving, the Co-Reviewer's Decision box shows `include`. | |
| C12 | Session B: record S2 **exclude** with reason `Spray, not rinse`, and S4 **exclude** with reason `No abstract to assess`. | On S2, after saving: `You and your Co-Reviewer recorded different decisions. This citation is held as a Conflict until the Owner resolves it.` Owner's Decision box shows `include: Adults, relevant`. | |
| C13 | Session A: PRISMA flow. | Matches **EXP-FLOW-CONFLICT**. | |
| C14 | Session B: Conflicts page. | S2 listed with both decisions and `Waiting for the Owner to resolve this Conflict.` No control to resolve it. | |
| C15 | Session A: Conflicts page. Both decisions are shown. The form starts on **Use Owner's decision** with `include` and the Owner's reason filled in. Pick **Enter a different decision**, set Final decision to **Exclude**, **clear** the pre-filled Reason, type `Spray is not a rinse`, **Resolve**. | After: `No outstanding Conflicts.` | |
| C16 | Session A: open S2. | Co-Reviewer's Decision box shows `exclude: Spray, not rinse`. | |
| C17 | Denied non-member. Session A: copy the URL of the **Solo** project. Session B: open it. In DevTools > Network find the `GET /review-projects/<id>` call. | Page: `Failed to load review project.` The call returns **403** with `Not authorized for this review project`. No Citation data appears. | |

### D. Full Text and extraction (Session A, Dual project)

| ID | Do | Expect | Result |
|---|---|---|---|
| D1 | S1: **Upload Full Text** `study-1-v1.pdf`. | Filename shown with **View / Download**. No parse warning. Full-Text Suggestion: `Preparing a Full-Text Suggestion…`, then `<decision>: <reason>`. Under Extraction Values, `Suggested: <value>` beside Sample size. Note the value (expected 40). | |
| D2 | S1: **Replace Full Text** with `study-1-v2.pdf`. | The old suggestion does not stay on screen. A new one is prepared for the new PDF. Note its Sample size (expected 48). | |
| D3 | S1: **View / Download**. | The served PDF opens in a new tab and reads `VERSION 2 (CORRECTED)`, not version 1. If the browser blocks the new tab, allow pop-ups for the site, click again, and record that it needed doing. | |
| D4 | S1, Sample size: click **Use** beside the suggestion (if none appeared, note it). Reload **without** saving. | Nothing was saved: the input is empty after the reload. **Use** only copies into the input. | |
| D5 | S1, Sample size: click **Use** again, then make sure the input reads `48` (type it if the suggestion differed, and note that). Click **Save**. Reload. | `Extraction value saved.` Value `48` is still there after the reload. | |
| D6 | S1, Full-Text Decision. | Nothing is selected before you choose, whatever the AI suggested. Choose **include**, **Save Full-Text Decision**: `Full-text decision saved.` | |
| D7 | S3: upload `study-3.pdf`. Full-Text Decision **exclude**, save without a reason. Then choose `Wrong population` from the reason list and save. | First: `Give a reason for the Exclude.` The list offers `Wrong population` and `Wrong study design`. Then: `Full-text decision saved.` | |
| D8 | Session B: open S1 and S3. | B sees the Full-Text Decisions and S1's `48`. This is expected: the Full-Text and extraction stage is **shared**, not independently blinded. | |

### E. Exports and counts

| ID | Do | Expect | Result |
|---|---|---|---|
| E1 | Session A: **Export CSV**. | Matches **EXP-CSV-DUAL-FINAL**. | |
| E2 | Session A: PRISMA flow. | Matches **EXP-FLOW-FINAL**, in the diagram and the Numeric Summary table. | |
| E3 | Session A: **Download as PNG**. | A file `prisma-flow-diagram.png` downloads, opens as an image, and shows the same numbers as E2. No `Failed to download PRISMA Flow Diagram as PNG.` | |
| E4 | Session B: **Export CSV**. | Same as E1 (B has now decided every Citation, so nothing is blinded). | |

### F. Host setting measured during this run

| ID | Do | Expect | Result |
|---|---|---|---|
| F1 | Run last, and only while no other Reviewer is using the host: it changes a host setting (an environment variable, so the deployed commit stays the same) and sends failed sign-ins that can lock everyone out of one shared rate-limit bucket for a few minutes. Measure `TRUSTED_PROXY_COUNT` with the procedure in `docs/deploy/render.md`, "Measuring `TRUSTED_PROXY_COUNT`". | Record the value kept and the status codes seen. | **2** (not 1 — see "Measured result" in `docs/deploy/render.md`). 0 and 1 both stayed `401` across 31 attempts (address rotates per request at both). At 2: 30×`401` then `429` on the 31st; different network got `401`; forged `X-Forwarded-For` repeat still got `429`. PASS. |

### G. Close out

| ID | Do | Expect | Result |
|---|---|---|---|
| G1 | Link the #65 restore-test records (Postgres and PDFs, isolated). This protocol did not restore or reset anything. | Links present, or noted as missing. | |
| G2 | Anthropic Console: usage after the run, minus the figure A0 recorded. | Recorded. Roughly 9 model calls; flag it if the difference looks larger. If A0 was missed, say so and fall back to the Console's per-day totals for the run's dates, labelled as a substitute. | |
| G3 | Post the result (below) on the release issue and link it from #65. Blur identities and secrets first. | Posted. | |

## Result to post

```
Pilot smoke run
Date:              YYYY-MM-DD
Operator:          <name or role>
Frontend commit:   <sha>   (asr-web deploy)
Backend commit:    <sha>   (asr-api deploy)
Intended release:  <sha>
Browser:           <name version>, Session A / Session B in <profiles or private window>
Provider:          real (Anthropic), model <ANTHROPIC_MODEL>; stubbed checks: none in this run
Model calls / usage difference: <n / amount>
Overall:           PASS | FAIL | PASS WITH CONCERNS

<the Steps tables, Result column filled in>

AI notes (informational, not pass/fail): B6 AI decision <..>, B10 agreed <..>,
  D1 suggested <..>, D2 suggested <..>, D5 typed by hand? <yes/no>

Failures and concerns: <step id, what happened, screenshot link>
Untested: <anything skipped, plus the standing list below>
Sign-off: <name>, <date>
```

## Not covered by this protocol

Record these as untested in every result, and add anything else skipped that run.

- The `generation_failed` AI state (the model call failing), the `parse_failed` state (a scanned PDF
  with no text layer), and a Full-Text Suggestion cut off as `truncated`.
- Possible Duplicates resolution and dismissal, Keep First merge mode, invitation revoke, Co-Reviewer
  removal and replacement, account removal and password reset (operator scripts).
- Search Terms, billing and the Account page (billing is off in the pilot).
- Rate limits beyond F1, request-size limits, RIS imports, and a CSV with skipped rows.
- Two Reviewers writing to the same Citation at the same moment, and any load or timing figure.
- Other browsers or phones, non-English text, keyboard shortcuts, and screen readers.
- Real-provider quality. This run checks that suggestions arrive, stay separate from the Reviewer's
  answer and stay blind in Dual, not that they are correct.
- **The Full-Text and extraction stage is shared, not independently blinded.** Either Reviewer can
  record a Full-Text Decision or an Extraction Value, and each sees the other's. This is the
  documented pilot scope (roadmap D4), not something this run can pass or fail.
- Backup and restore, which #65 records separately.
