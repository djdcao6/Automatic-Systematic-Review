# Use a Default-Workspace-scoped Anthropic API key, not an organization-scoped one

The Anthropic Console can issue either a single-workspace key (bound to one workspace, including the org's Default Workspace) or a multi-workspace/organization-scoped key. A multi-workspace key requires an `anthropic-workspace-id` header on every request, or the Messages API rejects it with a 400 (`"This API key is not scoped to a workspace..."`). We chose a Default-Workspace-scoped key for `backend/.env` so the backend's Anthropic client needs no workspace-header logic at all.

## Consequences

An organization-scoped key silently fails every Messages API call until the header is added, with an error that reads like an auth problem rather than a scope mismatch. A prior session was mid-way through diagnosing exactly this when an unrelated machine restart interrupted it, leaving the wrong-scoped key in place until this fix — worth recording so a future session doesn't have to re-diagnose the same 400 from scratch. If a key ever needs regenerating, pick "Default" (or a specific single workspace) in the Console, not an organization/multi-workspace key, unless the app is deliberately extended to send `anthropic-workspace-id`.
