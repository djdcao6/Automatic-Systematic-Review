# Removing an account deletes what it owns and anonymizes what it co-reviewed

The closed pilot has no delete routes, so the operator removes accounts on request (`backend/scripts/delete_account.py`, #62). A Reviewer can be the Owner of some Review Projects and the Co-Reviewer of others, and the two cannot be treated alike. We decided that the Review Projects the account owns are deleted whole (rows and PDFs), while a Review Project where it is only the Co-Reviewer is kept for its Owner: the account is detached the way an Owner's "remove Co-Reviewer" does it (#29), and its Screening Decisions stay. If any of its decisions, its side of a Conflict, or its former-Co-Reviewer mark remain in someone else's project, the account row is anonymized (email replaced by an unusable `deleted-<id>@deleted.invalid`, password replaced by one nobody knows) rather than deleted. An account with nothing left behind is deleted outright.

## Considered Options

- **Delete the Co-Reviewer's contributions too**: complete erasure, but it silently changes the Owner's Conflicts, flow diagram counts and CSV export, and leaves the project waiting for a replacement with less of the record than before. Rejected: the Owner did nothing to ask for that.
- **Refuse to delete an account that co-reviews anything**: simplest and safest to build, but every such request becomes manual work for the operator, and the request is then not honored until someone else acts.

## Consequences

- Deletion is not full erasure for a Co-Reviewer: the free-text reasons on their Screening Decisions stay with the Owner's review. The pilot terms must say so.
- A Co-Reviewer's existing sign-in token stays valid for its lifetime, since sign-in tokens name the account by id. Detaching them is what stops it opening the project, so the detach is not optional when an account is removed.
- Deleting an Owner also deletes their Co-Reviewer's work in that project. The script names the Co-Reviewer before it does so.
- Stripe is not changed by the script; the operator cancels any subscription there by hand.
