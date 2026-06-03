# Dashboard walkthrough — DBRE Console

Annotated tour of the operator dashboard (`dashboard/`), panel by panel, as it
renders the ESR B→C evidence pack. Use this alongside the screenshots when
recording the demo or writing the Devpost page.

## The screenshots (in `demo/screenshots/`)

Captured from the running dashboard:

| File | Shows |
|------|-------|
| `01-overview.png` | Full console at the **Approve** stage (fallback mode, the bundled example pack) — finding, recommendation, evidence hash, pending Approve |
| `02-responsive.png` | Narrow-viewport layout (panels stack) — proves the responsive grid |
| `03-verified-payoff.png` | The **payoff**: live + VERIFIED, all 5 stages green, Before (17,209 keys, red SORT) vs After (64 keys, no SORT, 2 ms) side by side |

To re-capture (no backend needed for the fallback shots):

```bash
cd dashboard && npm install && npm run dev   # http://localhost:3000
# then screenshot the running page, or drive headless Chrome:
#   chrome --headless --window-size=1280,760 --screenshot=out.png http://localhost:3000/
```

The verified payoff shot was produced by pointing `NEXT_PUBLIC_API_URL` at a mock
read endpoint serving a `verified` pack (status flipped, `after` filled).

## Panel-by-panel annotations

### Header — run identity + data source
The top bar shows the `run_id`, the namespace (`sample_supplies.sales_agent_demo`),
the pack `status`, and a **live / fallback** chip. `fallback` means it's rendering
the bundled example pack; `live` means it fetched from the deployed read API.

> Annotation: "Every view is one EvidencePack — the only thing the UI consumes."

### 5-stage indicator (`02-stages.png`)
**Detect → Diagnose → Test → Approve → Verify.** Completed stages show a green
check; the active stage pulses amber. For a `diagnosed` pack the first three are
done and it's waiting at **Approve**.

> Annotation: "Five visible stages over a phase-gated engine — the agent can't
> skip ahead or apply early."

### Predicted vs Observed (`03-plan.png`) — the centerpiece
Two columns, Before (serving index B) and After (recommended index C):
- **Stage chain** — each plan stage as a chip. `SORT` renders **red**, `IXSCAN`
  **green**, so the eye lands on the blocking sort immediately.
- **Metrics** — keys examined, docs examined, returned, millis. The
  *keys examined* figure is the headline: **17,209 (B) vs 64 (C)**.
- A **blocking sort / no sort** badge per column.

> Annotation: "The color *is* the diagnosis — red SORT on the left, gone on the
> right. 269× fewer index keys for the same 20 rows."

### Finding + Recommendation
- **Finding** — the root cause in plain language, with a severity badge and the
  evidence refs (e.g. `esr_wrong_B`).
- **Recommendation** — the exact `createIndex(...)` call and the ESR rationale.

> Annotation: "Gemini writes the narrative; the deterministic core computed the
> winner and the numbers."

### Approval Gate (`04-approve.png`)
First-viewport control surface for the **Human Operator / Judge**. It shows the
gate state, the mutation blocked/unblocked status, the **evidence hash** (what the
approval is bound to), and **Approve** / **Reject** buttons when pending. After a
decision the gate closes as verified/rejected — no double-submit.

> Annotation: "The human gate. The approval is signed against this exact evidence
> hash — change the evidence, and the old approval is void."

## Visual identity (why it looks like this)
Deliberately not a stock template: **JetBrains Mono + IBM Plex Sans**, Phosphor
icons, a dark slate palette where colors carry query-plan meaning (amber =
pending, green = good plan, red = regression). Full rationale in
`dashboard/README.md`. It should read as an instrument an SRE trusts to approve a
production change — not a CRUD app.
