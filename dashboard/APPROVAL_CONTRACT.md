# Approval API — proposed contract (#26 ↔ #29)

The dashboard's Approve/Reject action (#26) needs an agreed request/response
shape from the approval API route (#29, owned by @d3v07). This is the dashboard's
**proposal** — please confirm or amend, then we lock it. The dashboard builds
against `lib/approval.ts`, where the endpoint path + body shape are isolated to
one place, so adjusting to the final shape is a small, contained change.

## Why `evidence_hash` is the key

Per `contracts/README.md`, `evidence_hash` binds `before` + `recommendation` —
it pins *what gets applied given what evidence*. A human approval signs off on
exactly that hash. So the request **must** carry the hash the operator saw, and
the server **must** reject if it no longer matches the current pending pack
(the pack changed under the operator's feet).

## Proposed request

```
POST {NEXT_PUBLIC_API_URL}/packs/{run_id}/decision
Content-Type: application/json

{
  "decision": "approve" | "reject",
  "evidence_hash": "<the hash shown in the UI>",
  "approver": "<operator id; 'dashboard-operator' until auth exists>",
  "note": "<optional free text, e.g. reject reason>"
}
```

## Proposed responses

| Status | Meaning | Body |
|--------|---------|------|
| `200` | recorded | the **updated EvidencePack** (status now `approved`/`rejected`, `decision` populated) — lets the UI re-render from the source of truth |
| `409` | `evidence_hash` no longer matches the pending pack | `{ "error": "stale_evidence_hash", "current_hash": "..." }` |
| `404` | unknown `run_id` | `{ "error": "not_found" }` |
| `4xx/5xx` | other | `{ "error": "<code>", "message": "..." }` |

Returning the full updated pack on `200` is preferred (the dashboard just
re-renders it). If that's heavy, a minimal `{ status, decision }` also works —
tell us which and we'll match it.

## What the dashboard does with it

- On `200`: show the approved/rejected state, disable the bar (no double-submit),
  and refresh the pack view.
- On `409`: tell the operator the evidence changed and to re-review (do **not**
  silently retry).
- On network/5xx: show an inline error, keep the button re-enabled to retry.

## Open questions for @d3v07

1. Endpoint path — `/packs/{run_id}/decision`, or do you prefer
   `/approve` + `/reject` as separate routes?
2. Does `200` return the full updated pack, or a minimal status object?
3. Any auth header needed now, or is `approver` in the body enough for the demo?
