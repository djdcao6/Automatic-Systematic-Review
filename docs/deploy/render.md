# Deploying the pilot on Render

Runbook for #65. `render.yaml` at the repo root is the source of truth for what gets created; this
page says how to create it, run it, back it up and restore it. Facts about Render were read from
its site on 2026-09-20 (sources at the end) and prices change, so check the pricing page when you
sign up.

## What this creates

| Piece | Render service | Plan | About per month |
|---|---|---|---|
| Backend (FastAPI) | Web service `asr-api`, Docker, 5 GB persistent disk at `/data` | 1 CPU, 2 GB | $25 + $1.25 disk |
| Database | Postgres `asr-db` (17), private network only, 5 GB storage | Basic, 256 MB | about $6 + $1.50 storage |
| Frontend (Next.js) | Web service `asr-web`, Node | 0.5 CPU, 512 MB | $7 |
| Workspace | Hobby | | $0 |

About $41 a month, all in `ohio`. Storage is billed at $0.30 per GB for the database and $0.25 per
GB for the disk. The Blueprint screen shows the exact prices; the $6 for the 256 MB database is
worked out from Render's own examples, so check it there. Add the Anthropic spend cap (start near
$45) and a domain to reach the roughly $100 ceiling the owner chose for decision D2 in roadmap #88
(host, region and budget).

Why it looks like this:

- **Small database and disk.** D2 first chose Postgres Basic 1 GB with a 10 GB disk. On 2026-09-21
  the owner cut it to 256 MB and 5 GB each, to save about $17 a month. Render's default storage for a
  Basic database is 15 GB, and storage on both the database and the disk can grow but never shrink,
  so they start small. If imports get slow, move the database to `0.5c-1g`; if PDFs fill the disk,
  raise `sizeGB` in `render.yaml` (Render may restart the service to resize).
- **One backend instance.** Full Text files are PDFs on local disk and rows store their paths, and
  the sign-in and sign-up rate limits live in the process. A Render disk allows exactly one
  instance, and turns off zero-downtime deploys, so every backend deploy has a short gap.
- **US region.** Render has no Canadian region (Oregon, Ohio, Virginia, Frankfurt, Singapore).
  D2 assumed Reviewers in the US and Canada; pilot terms must tell Canadian Reviewers their data is
  stored in the US. If a Reviewer in the EU joins later, revisit the region: moving it means new
  services and a data migration.
- **No patient data.** Render's Terms of Service forbid storing HIPAA health information, payment
  card data and government ID numbers. Pilot terms must tell Reviewers not to upload any.
- **Deploys are manual** (`autoDeployTrigger: "off"`), so a merge never deploys by itself and you
  choose which commit goes live.

## Before you start

- A Render account on the Hobby workspace, with the GitHub repo connected.
- An Anthropic API key scoped to the Default Workspace (ADR 0002), with a **monthly spend cap set in
  the Anthropic Console**. A hung or abused key should stop at the cap, not at your card.
- The pilot Reviewers' emails for `SIGNUP_ALLOWLIST` (comma-separated). Empty means nobody can
  register.
- Optional: a domain (see "Custom domain"). Without one the services live at
  `https://<name>.onrender.com`, which Render serves over HTTPS.

## First deploy

1. In Render: **New > Blueprint**, pick this repo, branch `main`. Render reads `render.yaml` and asks
   for the values marked `sync: false`.
2. Enter `ANTHROPIC_API_KEY` and `SIGNUP_ALLOWLIST`. For `FRONTEND_ORIGIN` and `NEXT_PUBLIC_API_URL`
   enter `https://asr-web.onrender.com` and `https://asr-api.onrender.com` as a first guess.
3. Render creates all three and deploys them. If a service name was taken, Render adds a suffix:
   read the real URLs from the dashboard. If the first `asr-api` deploy fails at the pre-deploy step
   because the database was still starting, **Manual Deploy** it again.
4. If the real URLs differ from your guess, correct `FRONTEND_ORIGIN` on `asr-api` and
   `NEXT_PUBLIC_API_URL` on `asr-web`, then **Manual Deploy** both. The frontend needs a rebuild
   because that value is baked into the browser bundle; the backend needs it for CORS.
5. Smoke test (the checklist in #65), in this order:
   - `https://<api>/health` returns `{"status": "ok"}`, and the `asr-api` deploy log shows the
     pre-deploy command `alembic upgrade head` succeeding.
   - Open the frontend and register with an allowlisted email.
   - Create a Review Project, import a CSV of Citations, screen a Citation.
   - Attach a Full Text (upload a PDF) and open it again. This also proves `/data` is writable: the
     container runs as root because the disk's ownership is not documented for other users.
   - Export.

   The full two-reviewer run, with fixed data and expected values, is `docs/testing/pilot-smoke.md`
   (#93).
6. Do the two restore tests below **before inviting anyone**. The PDF one is destructive and only
   safe while the disk holds nothing real.

## Custom domain (optional)

Add each domain to its service in the dashboard and create the DNS records Render shows; Render
issues the HTTPS certificate. Then set `FRONTEND_ORIGIN` on `asr-api` to the frontend's new origin
and `NEXT_PUBLIC_API_URL` on `asr-web` to the API's new origin, and **Manual Deploy** both.
`FRONTEND_ORIGIN` accepts **exactly one origin** (CORS allows only that one), so once it names the
custom domain the `onrender.com` address stops working for the app in a browser.

## Environment variables

| Variable | Set by | Note |
|---|---|---|
| `DATABASE_URL` | Blueprint, from `asr-db` | Render's plain `postgresql://` URL; the app switches it to the `psycopg` driver |
| `JWT_SECRET_KEY` | Blueprint, generated | Rotating it signs everyone out |
| `ANTHROPIC_API_KEY` | You | Default-Workspace key (ADR 0002) |
| `ANTHROPIC_MODEL` | Blueprint | `claude-haiku-4-5` |
| `FULL_TEXT_STORAGE_PATH` | Blueprint | `/data/full_texts`, on the persistent disk |
| `FRONTEND_ORIGIN` | You | Exact frontend origin, no trailing slash |
| `SIGNUP_ALLOWLIST` | You | Pilot emails |
| `BILLING_ENABLED` | Blueprint | `false`; Stripe settings stay unset |
| `TRUSTED_PROXY_COUNT` | Blueprint | `2`, measured during the #93 smoke run, see below |
| `TEST_DATABASE_URL` | **never** | Only the test suite uses it, and it resets that database |
| `NEXT_PUBLIC_API_URL` | You, on `asr-web` | Build-time; a change needs a redeploy |

## Routine deploys

Merge to `main`, wait for CI, then **Manual Deploy** (choosing that commit) on `asr-api` and
`asr-web`. Migrations run before the new backend takes traffic, and a failing migration stops the
deploy. Expect a short outage on each backend deploy (see above). Rolling back code does not roll
back a migration: if a migration was bad, restore the database (below) instead of guessing a
downgrade.

## Operator tasks

Open a shell on `asr-api` (dashboard **Shell**, or SSH). The scripts from ADR 0008 are in `/app`:

```
python scripts/delete_account.py --help
python scripts/delete_project.py --help
python scripts/reset_password.py --help
```

`psql` is installed for looking at the database; use the connection strings on the database's
**Info** page.

## Backups: what protects against what

| Layer | Covers | Window | Restores to |
|---|---|---|---|
| Postgres point-in-time recovery (paid databases) | Bad migration, dropped table, bad delete | 3 days on Hobby (7 on Pro) | A **new** database instance; not within 10 minutes of now |
| Postgres logical backup (dashboard export) | The same, plus a copy you can keep | Render keeps them 7 days | A new database from the download |
| Disk snapshots (automatic, daily) | Lost or corrupted PDFs | At least 7 days | The **same disk**, whole disk, and everything since the snapshot is lost |

Gaps, stated plainly:

- **Off-platform copy.** Everything above lives on Render. Weekly, download a logical backup from the
  dashboard and keep it somewhere else. There is **no documented way to copy the PDF disk out**
  (the SSH docs mention no `scp`, `rsync` or `sftp`), so Full Text files have no off-platform copy
  yet. For a closed pilot most can probably be attached again by the Reviewer who added them, which
  limits the loss; automating a copy from inside the service is a follow-up.
- **Snapshot restore is in place.** An isolated restore, as roadmap #88 asks, is not something the
  docs describe for disks. The test below therefore runs in place, before real data exists.
- **The two backups are not taken together.** Restoring the database alone leaves rows pointing at
  PDFs that may not be on the disk, and restoring the disk alone does the reverse. After either
  restore, check that each Full Text opens before letting Reviewers back in.

## Restore tests (evidence for #65)

Record each result: date, what you did, how long it took, the age of the backup, and what you saw.
Roadmap #88 wants "a successful isolated restore of Postgres and PDFs, with a restored PDF actually
opened": the database test proves the rows, and the PDF test proves a restored PDF opens.

**Database (isolated).**
1. With test data in place, note the row counts of `reviewers`, `review_projects`, `citations`.
2. `asr-db` > **Recovery** > **Restore Database** to a time at least 10 minutes ago, named
   `asr-db-restore-test`. Time it.
3. From a shell on `asr-api`, run `psql` with the restore instance's internal URL from its **Info**
   page and compare the counts and the newest `created_at`.
4. Delete `asr-db-restore-test` so it stops billing.

**PDFs (in place, before real data).**
1. Attach PDF A to a Citation. Wait for the next daily snapshot (24 hours).
2. Attach PDF B to another Citation.
3. **Disks** page of `asr-api` > restore that snapshot.
4. In the app, open PDF A's Full Text: it must open. PDF B's Full Text is still in the database
   (only the disk was restored), but its file must no longer open. Record the time taken.

## Measuring `TRUSTED_PROXY_COUNT`

Render's docs do not say how many proxies sit in front of the app, so the Blueprint used to default
to 0: every visitor then shares one per-IP bucket (30 sign-ins per 5 minutes, 10 sign-ups per hour),
which is safe but lets one visitor lock out the rest. A value that is too high is worse, because it
trusts an address the client wrote. Measured during the #93 smoke run:

1. Set `TRUSTED_PROXY_COUNT=1` and redeploy the backend.
2. From your own network, send 31 failed sign-ins for 31 different emails to `/login`
   (the per-IP limit is 30, the per-email limit 10). The 31st should get `429`.
3. From a different network (a phone on mobile data), send one failed sign-in. `401` means each
   visitor has their own bucket, so 1 is right. `429` means both networks share a bucket, so try 2.
4. With the value you kept, repeat step 2 with a forged `X-Forwarded-For: 203.0.113.9` header. Still
   `429` means the forged left-hand address is ignored, as intended.

**Measured result: 2, not 1.** At both `0` and `1`, step 2 never tripped `429` across 31 attempts —
`request.client.host` (used at `0`) and the rightmost `X-Forwarded-For` hop (used at `1`) both come
from an internal Render layer with more than one node, so the address seen by the app rotates per
request even for the same real visitor. A temporary debug log of the raw header (removed after, not
on `main`) showed exactly two comma-separated hops on every request: a stable leftmost entry (the
real client, written by Render's edge) and a rotating rightmost entry (the internal layer). Only
`TRUSTED_PROXY_COUNT=2` reads the stable leftmost entry (`hops[-2]`). With `2`: 31-request test gave
`401` × 30 then `429` on the 31st; a different network got `401` (own bucket, confirming 2 is not
too high); the forged-header repeat still got `429`. If Render's edge topology changes, re-measure —
don't assume 2 holds forever.

## Finishing #65

The Blueprint and this page are only part of #65. Before closing it, link on the issue: the
deployed two-reviewer smoke result from #93 (protocol: `docs/testing/pilot-smoke.md`), the two
restore-test records above, and the release instructions in #64. Host availability is what #93
waits on; closing #65 is not.

## Known gaps

- Container runs as root; drop privileges once the disk's ownership has been checked on a real
  service.
- No off-platform copy of the Full Text files, and no automation of the database export.
- No alerting: check the dashboard, or add a health check notification, before the pilot starts.
- Hobby has a 3-day database recovery window and one team seat.

## Sources (read 2026-09-20)

- Prices, plans, workspace features: https://render.com/pricing
- Regions: https://render.com/docs/regions
- Disks and snapshots: https://render.com/docs/disks
- Postgres recovery and backups: https://render.com/docs/postgresql-backups
- Blueprint fields and plan names (storage sizes and the no-shrink rule re-read 2026-09-21):
  https://render.com/docs/blueprint-spec
- Shell and SSH access: https://render.com/docs/ssh
- Terms of Service (sensitive data): https://render.com/terms
