# DBRE Console — dashboard (#10)

Operator dashboard for the Evidence-Driven DBRE agent. One route renders an
**EvidencePack** (the ESR B→C scenario): the 5-stage pipeline, the before/after
explain comparison, the finding + recommendation, and an Approve action.

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
`controller/`, `agents/`, or any backend module. For now the page reads the
committed example pack (`lib/example_pack.json`); Day 3+ swaps that for the live
read endpoint (#18) with no shape change.

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
  StageIndicator    Detect → Diagnose → Test → Approve → Verify
  PlanPanel         before/after explain (keys examined, stage chain, sort flag)
  EvidencePanel     finding (severity) + recommendation (index spec + rationale)
  ApproveBar        evidence hash + Approve button (inert until Day 3+)
lib/
  evidence.ts       EvidencePack v1 types + helpers
  example_pack.json committed sample pack (static data source)
```
