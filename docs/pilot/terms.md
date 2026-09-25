# Pilot participant terms

**Draft — not reviewed, not published, not linked from the app yet.** This is a first pass
for the founder to review, cut, and rewrite before it goes anywhere near a real participant.
It is not legal advice and has not been checked by anyone with legal training.

This is meant to be shown to every Reviewer before or during registration — either as the
text near the AI-disclosure checkbox, or as a separate page linked from it. It covers
consent and data handling only; it is not a Terms of Service for a commercial product,
because the pilot is invitation-only and free.

---

## What this covers

You're being invited to try Automatic Systematic Review during its closed pilot. Before you
start, here's what happens to what you put into it.

**The pilot is invitation-only and free.** You need an invitation from the operator or from
an existing Reviewer on your Review Project. There is no cost during the pilot.

**AI disclosure.** Abstracts, PDFs and criteria you add are sent to Anthropic's API to
generate suggestions. AI suggestions are always shown separately from your own decision and
never fill in a decision for you — you decide, always. Anthropic handles that data under its
own terms and privacy policy, not these terms. Don't upload patient-identifiable data.

**Do not upload PHI or any patient-identifiable data.** This includes names, dates of birth,
medical record numbers, or anything else that could identify a real patient — in an abstract,
a PDF, a criteria note, or anywhere else in the app. The pilot's hosting does not support
storing it, independent of this rule.

**Where your data lives.** The app runs on Render, hosted in the United States (Ohio). If
you're in Canada, your data is stored in the US, not in Canada. Backups (database and PDFs)
are also on Render, in the same region. There is currently no off-platform copy of uploaded
PDFs — see "What we don't yet do" below.

**Who can see your work.** The Owner of a Review Project and any Reviewer they invite to it
can see that project's citations, decisions and exports, per the app's Dual-review blinding
rules (your own screening decision stays hidden from your Co-Reviewer, and theirs from you,
until you've both decided). The operator (the founder) can access the database and files to
run backups, restore tests, and the account/project tools described below — not to read your
screening decisions for any purpose other than operating the pilot.

**Quebec residents cannot currently join this pilot.** Quebec's Law 25 sets requirements this
hosting setup does not meet. The operator asks each invitee where they are based before adding
them, and does not add anyone in Quebec. The app itself does not check location.

**Account and data removal.** There is no self-service delete yet. If you want your account
or a project removed, ask the operator — removal deletes the account's or project's rows and
any attached PDFs. This is a manual, on-request process during the pilot, not an automated
one.

**This is a pilot, not a finished product.** Features, data retention, and the tool itself
may change without notice while the pilot runs. Don't rely on it as the only copy of your
work — keep your own copy of anything you can't afford to lose (search strategies,
extracted data, exports).

**Questions or a removal request:** djdcao6@gmail.com.

---

## What we don't yet do (say plainly, don't gloss over)

- No off-platform copy of uploaded PDFs. If Render's disk is lost beyond what its automatic
  snapshots cover, PDFs may need to be re-uploaded by the Reviewer who added them.
- No email notifications (invitations, password resets) — these happen by the operator
  contacting you directly.
- No independent legal or security review of this pilot has been done.

---

## Notes for the founder, not for participants (delete before publishing)

- This draft assumes the pilot stays invitation-only and free the whole time it's in effect —
  if the free-core/paid-AI model (roadmap decision, approach C) goes live before these terms
  are rewritten, the "free during the pilot" line and the billing silence both need revisiting.
- Consider whether you want a Reviewer's explicit acknowledgment of this whole page (not just
  the existing one-sentence AI-disclosure checkbox) before they can be added to a project —
  that's a product decision, not something this draft can decide for you.
- The "who can see your work" paragraph describes today's blinding rules faithfully but is
  not exhaustive — cross-check it against `CONTEXT.md` and the relevant ADRs before publishing,
  in case a rule has since changed.
- This file is committed but **not yet linked from anywhere in the app** — a Reviewer has no
  way to find this page yet. That's a separate follow-up.
