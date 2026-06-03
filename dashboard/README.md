# DBRE Console — dashboard (#10)

Operator dashboard for the Evidence-Driven DBRE agent. One route renders an
**EvidencePack** (the ESR B→C scenario): the 5-stage pipeline, the before/after
explain comparison, the finding + recommendation, the approval-bound evidence
hash, the first-class approval gate, Agent Engine/controller trace, and the
approve/reject action.

## Run

```bash
cd dashboard
npm install
npm run dev        # http://localhost:3000
```

Build check: `npm run build`.

## Contract boundary

Per [`../contracts/README.md`](../contracts/README.md) the dashboard consumes
**`EvidencePack` JSON only** — the type lives in [`lib/evidence.ts`](lib/evidence.ts),
mirroring `contracts/evidence_pack.schema.json`. It does **not** import
`controller/`, `agents/`, or any backend module.

## Data source (#25)

The page loads a pack via [`lib/api.ts`](lib/api.ts) → `loadPack()`:

1. If `NEXT_PUBLIC_API_URL` is set, it fetches `GET {API_URL}/packs/{run_id}`
   (`cache: no-store`).
2. `run_id` comes from the `?run_id=` query param, else `NEXT_PUBLIC_PACK_ID`,
   else the example pack's own id.
3. On **any** failure — unset URL, 404, non-OK, or network error — it falls back
   to the committed `lib/example_pack.json` and shows a notice in the footer. A
   `live`/`fallback` chip in the header reflects which source rendered.

This means it works today with zero config (fallback) and **auto-upgrades to live
data** the moment `NEXT_PUBLIC_API_URL` points at the deployed read API (#31) —
no component or contract changes.

| Env var | Purpose |
|---------|---------|
| `NEXT_PUBLIC_API_URL` | Base URL of the read API (#31). Unset → fallback mode. |
| `NEXT_PUBLIC_PACK_ID` | Default `run_id` to request when none is in the URL. |

## Visual identity (non-default — AC requirement)

This deliberately avoids the stock Next.js look (no Inter, no Lucide, no
purple gradient). The chosen identity is a **dark engineering-operations
console**, fitting a database-reliability instrument:

| Element | Choice | Why |
|---------|--------|-----|
| Display / data font | **JetBrains Mono** | Monospace echoes `explain` output and index specs; reads as an engineering tool, not a marketing site. |
| Body font | **IBM Plex Sans** | Humanist sans that pairs cleanly with the mono without defaulting to Inter. |
| Icons | **Phosphor** | Distinct from the default Lucide set; consistent weight options. |
| Palette | Deep slate (`#0d1117`) base; **amber** = pending/attention, **green** = good plan, **red** = regression/blocking, **cyan** = neutral data | Colors are borrowed from query-plan semantics — a `SORT` stage renders red, `IXSCAN` green — so the UI *means* something, not just decoration. |
| Texture | Faint 44px grid over the background | Subtle "instrument panel" feel; avoids a flat stock dark theme. |

The one-line why: **it should look like a serious performance-engineering
instrument an SRE would trust to approve a production index change** — not a
generic CRUD app.

## Structure

```
app/
  layout.tsx        fonts + metadata
  page.tsx          the agent-run route (assembles the panels)
  globals.css       design tokens (palette, fonts) + reset
  page.module.css
components/
  ApprovalGatePanel first-viewport human gate + hash-bound approve/reject
  StageIndicator    Detect → Diagnose → Test → Approve → Verify
  TracePanel        EvidencePack hash + Agent Engine/controller/human trace
  PlanPanel         before/after explain (keys examined, stage chain, sort flag)
  EvidencePanel     finding (severity) + recommendation (index spec + rationale)
lib/
  evidence.ts       EvidencePack v1 types + helpers
  example_pack.json committed sample pack (static data source)
```

## Live workflow

- The first viewport renders the **Approval Gate**. It is visible before and after
  diagnosis; during a run it is collecting evidence, then it moves to pending
  approval with the required hash.
- **Ask the agent** calls the same-origin `/api/run` proxy, which forwards to the
  Cloud Run API with the server-side token. The backend opens the approval gate
  first, then asks Agent Engine for read-only diagnosis.
- The returned pack is `diagnosed`, shown as **pending approval**. No database
  mutation happens during this step. `agent_trace` starts with `approval_gate/gate`,
  then shows Agent Engine tool events plus deterministic validation.
- **Approve fix** posts the displayed `evidence_hash` through the same-origin
  decision proxy. The backend issues a one-time approval ticket and applies/verifies
  the index only after that hash-bound approval. If the API is not configured, the
  UI shows an error and does not fake a saved decision.
- The trace panel and footer show when the pack came from the live API, where the
  EvidencePack aggregate and internal ledger event collections are persisted.
