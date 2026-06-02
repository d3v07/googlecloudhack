# Demo script — the B→C ESR reveal (~3 min)

The story: a query is silently slow because the "obvious" index sorts in memory.
The agent reads the real `explain`, predicts the correct **ESR** index, a human
approves, and the fix is verified — every step backed by a hashed evidence pack.

All numbers below are the measured fixture results
(`seed/fixtures/fixture_results.golden.json`, 300k docs, seed=42).

---

## 0:00–0:15 — Hook

> "This is a database agent that doesn't just *suggest* an index — it proves the
> fix with evidence, and it won't touch production until a human signs off."

On screen: the DBRE Console, one run loaded, the 5-stage bar
(Detect → Diagnose → Test → Approve → Verify).

## 0:15–0:40 — Detect + the trap

> "Here's a real query on a 300,000-document collection — filter by store, range
> on customer age, sorted by date. There's already an index on it. But it's
> slow."

Show the query and **Index B** — the obvious choice:
`{ storeLocation, customer.age, saleDate }`. Looks reasonable: all three fields
are covered.

## 0:40–1:30 — Diagnose: the agent reads the evidence

> "The agent pulls the actual execution plan. Index B puts the *range* field
> before the *sort* field — so MongoDB can't use the index order. It loads every
> match and sorts them in memory."

On screen, the **Before** panel:
- stage chain `FETCH → SORT → IXSCAN` (the `SORT` node is **red**)
- **17,209 index keys examined** + a blocking in-memory sort

> "That blocking SORT is the bug. The agent's finding says exactly that."

## 1:30–2:10 — Test: the predicted fix

> "It proposes the ESR-ordered index — Equality, then Sort, then Range:
> `{ storeLocation, saleDate, customer.age }` — and *predicts* the plan will lose
> the sort stage entirely."

This is the **prediction** — state it before showing the result.

## 2:10–2:35 — Approve: the human gate

> "Nothing gets applied automatically. The operator sees the evidence pack — and
> its hash — and approves. The approval is bound to that exact evidence hash; if
> the evidence changed, the approval is rejected."

Click **Approve fix**. The bar settles to the approved state.

## 2:35–3:00 — Verify: predicted vs observed

> "Now the observed result fills in next to the prediction."

The **After** panel:
- stage chain `LIMIT → FETCH → IXSCAN` — **no SORT**
- **64 index keys examined** — down from 17,209. **~269× fewer.**

> "Predicted: no sort. Observed: no sort. Same 20 rows, 269 times less work — and
> every step is in a signed evidence pack you can audit. That's the difference
> between an agent that guesses and one that proves."

---

## The one-sentence pitch

> An evidence-driven MongoDB performance engineer: it diagnoses the real plan,
> predicts the ESR fix, gates the apply behind human approval, and ships a hashed
> evidence pack for every change.

## Headline numbers (for slides / Devpost)

| | Index B (obvious) | Index C (ESR) |
|---|---|---|
| index order | Equality, **Range**, Sort | Equality, **Sort**, Range |
| blocking in-memory sort | **yes** | **no** |
| index keys examined | **17,209** | **64** |
| rows returned | 20 | 20 |

**~269× fewer index keys examined, blocking sort eliminated, identical results.**
