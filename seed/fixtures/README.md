# Primary fixture — B-vs-C ESR index trap (#9)

The hard diagnostic gate for the demo. We seed a workload on the `target` cluster
where the **obvious** index loses to the **correct ESR-ordered** index for one
query. The agent must recommend **C**, not **B** — and the `explain` evidence below
proves which is right, deterministically.

## The query under test

```js
db.sales_agent_demo.find(
  { storeLocation: "Denver", "customer.age": { $gte: 30, $lte: 50 } }
).sort({ saleDate: -1 }).limit(20)
```

It contains all three **ESR** ingredients:

| Role         | Field            | In the query                       |
|--------------|------------------|------------------------------------|
| **E**quality | `storeLocation`  | `== "Denver"`                      |
| **S**ort     | `saleDate`       | `sort({ saleDate: -1 })`           |
| **R**ange    | `customer.age`   | `{ $gte: 30, $lte: 50 }`           |

The `.limit(20)` is the amplifier: with a sort-providing index the engine can stop
after collecting 20 matches; without one it must read **every** match and sort them
before it can apply the limit.

## The two candidate indexes

```js
// Index B — the OBVIOUS choice, but WRONG (Range placed before Sort)
{ storeLocation: 1, "customer.age": 1, saleDate: -1 }   // name: esr_wrong_B

// Index C — the CORRECT ESR order (Equality, Sort, Range)
{ storeLocation: 1, saleDate: -1, "customer.age": 1 }   // name: esr_right_C
```

Why B is a trap: it *looks* reasonable — equality, range, and sort fields are all
present, and a common instinct is "filter fields first, sort field last." But
because the **range** (`customer.age`) sits **before** the **sort** key
(`saleDate`), the index can no longer return rows in `saleDate` order, so MongoDB
must collect every matching key and run a **blocking in-memory SORT**.

C places the sort key immediately after the equality key, so the index itself
yields rows already in `saleDate` order. No sort stage; the engine walks the index
and stops once it has 20 rows.

## Observed `explain` (executionStats) — measured, 300,000 docs, seed=42

| Plan                 | winningPlan stages        | Blocking SORT? | **keysExamined** | docsExamined | nReturned |
|----------------------|---------------------------|----------------|-----------------:|-------------:|----------:|
| No index (COLLSCAN)  | `FETCH → SORT → COLLSCAN` | yes            | 0                | 300,000      | 20        |
| **Index B** (wrong)  | `FETCH → SORT → IXSCAN`   | **yes**        | **17,209**       | 20           | 20        |
| **Index C** (correct)| `FETCH → IXSCAN`          | **no**         | **64**           | 20           | 20        |

**Read the `keysExamined` column, not `docsExamined`.** Because of the `.limit(20)`,
the `FETCH` stage runs *after* the sort+limit, so both index plans fetch only ~20
documents — `docsExamined` hides the real cost. The true work is in the index scan:

- **Index B** must scan **17,209** index entries (every Denver buyer aged 30–50)
  and then **blocking-sort** all of them before taking the top 20.
- **Index C** walks the index already in `saleDate` order and stops after **64**
  keys — **no sort stage at all**.

That's a **~269× reduction in index keys examined** plus elimination of a blocking
sort, for an identical 20-row result. This delta is the "predicted vs observed"
payload the agent's evidence pack is built around.

## How to load / reproduce (one command)

Connection string comes from the environment (never hard-coded):
`MONGODB_TARGET_URI`, or `MONGODB_VERIFY_USER` / `MONGODB_VERIFY_PW` as a dev
fallback.

```bash
# seed 300k docs -> build indexes B & C -> run explain comparison -> write golden
uv run python seed/seed_demo_fixture.py --all
```

Individual steps: `seed`, `indexes`, `verify`, `golden`
(e.g. `uv run python seed/seed_demo_fixture.py verify`). Use `--count N` to seed a
different size while iterating.

> **Note on doc shape:** the seeded docs are intentionally slim — only
> `storeLocation`, `saleDate`, `customer.age`, `purchaseMethod`. The real `sales`
> doc carries a large `items` array the trap never touches, and the M0 free tier is
> capped at 512 MB. The ESR trap is a property of index *structure* vs the query's
> equality/sort/range fields, so the slim docs produce identical plans while fitting
> the free tier with room to spare.

## Acceptance contract (asserted by `verify`, fails loudly otherwise)

- [x] **B uses a blocking in-memory SORT** (`hasSort == true`)
- [x] **C has no sort stage** (`hasSort == false`)
- [x] **C examines far fewer index keys than B** (64 vs 17,209)
- [x] **The keys-examined gap is large** (≥ 10×; measured ~269×)
- [x] **Both return the same rows** (`nReturned == 20` for each)
- [x] **C uses the correct ESR index** (`esr_right_C`)

## Determinism & the golden file

`seed/fixtures/fixture_results.golden.json` records the query, both index
definitions, the structural explain results above, and a `fixtureHash` (SHA-256
over the canonical JSON of everything *except* wall-clock timings, which are
environment-dependent and deliberately excluded). Re-running `golden` against the
same seeded data reproduces a byte-identical hash, so downstream fixture-contract
tests can assert against it.
