# MongoDB MCP Capability Check (Issue #3)

**Owner:** @Frex22 · **Date:** 2026-05-30 · **Status:** complete
**MCP server:** `mongodb-js/mongodb-mcp-server` v1.11.0 (commit `40e6e43`)
**Cluster under test:** `target` (M0, GCP CENTRAL_US, MongoDB 8.0.23)
**How tested:** drove the real MCP stdio JSON-RPC protocol (`initialize` → `tools/list`
→ `tools/call`) against `target`. Reads ran on `sample_supplies.sales` (5,000 docs);
write tools ran on a scratch namespace (`mcp_smoketest.scratch`, dropped after) so demo
data was untouched. Script: `tests/mcp/mcp_smoke.py`.

## Required tools — result

| Tool | Present | Smoke test on `target` | Notes |
|------|:---:|---|---|
| `explain` | ✅ | ✅ PASS | `executionStats` verbosity returns `explainResult` — this is the heart of Diagnose/Test stages. |
| `find` | ✅ | ✅ PASS | Returned 1 of 5,000 docs; honors `limit`. |
| `count` | ✅ | ✅ PASS | 5,000. |
| `aggregate` | ✅ | ✅ PASS | `$count` pipeline returned correctly. |
| `collection-schema` | ✅ | ✅ PASS | Returns `schema` + `fieldsCount` (sampled). |
| `collection-indexes` | ✅ | ✅ PASS | Returns classic + search index arrays. |
| `create-index` | ✅ | ✅ PASS | Created classic index `smoke_x` on scratch coll. |
| `drop-index` | ✅ | ✅ PASS | Dropped it. Has a **human-confirmation gate** (`getConfirmationMessage`) — relevant to our Approve stage. |
| `mongodb-logs` | ✅ registered | ❌ **FAILS on M0** | See Gap 1. |
| `atlas-get-performance-advisor` | ❌ **not registered** | ❌ unavailable | See Gap 2. |

**8 of 10 work cleanly. The 2 that don't are both the Atlas/observability path, and both
were already anticipated as M10-gated in the build plan.** Tool registry total: 48 tools in
source; 25 exposed in our run (Atlas-family tools require API credentials to register — see Gap 2).

## Gap 1 — `mongodb-logs` does not work on M0 (NEW finding, affects plan)

- **Symptom:** MCP returns output-validation error (`totalLinesWritten` expected number,
  received undefined).
- **Root cause (verified directly):** the tool calls `db.adminCommand({getLog: "global"})`.
  On the M0 shared tier this returns `{ ok: 1, log: [], totalLinesWritten: <absent> }` — the
  command succeeds but Atlas exposes **no log lines and omits `totalLinesWritten`** on shared
  tiers. The MCP server's output schema requires `totalLinesWritten: number`, so it raises a
  validation error. Not an MCP bug and not an auth failure — it's that M0 returns no log data.
- **Impact on the plan:** the build plan's Detect-stage risk mitigation says *"`mongodb-logs`
  is the real-call-path fallback; fixture is the always-works fallback"* when Performance
  Advisor is unavailable on a cost-cut M0. **But on M0 `mongodb-logs` is also unavailable** —
  so on the current cluster, the **fixture is the *only* Detect path**. Real-log Detect needs
  M10+.
- **Fallback:** demo Detect reads from the seeded fixture (as planned). For a "real call path"
  we'd need M10 (enables `getLog` + Performance Advisor slow-query logs).

## Gap 2 — `atlas-get-performance-advisor` requires API creds + M10

- **Symptom:** tool is not in `tools/list` at all (`Tool ... not found` on call).
- **Root cause:** the Atlas-family tools only register when the server is started with Atlas
  API credentials (`MDB_MCP_API_CLIENT_ID` / `MDB_MCP_API_CLIENT_SECRET` — an Atlas
  **Service Account**). We started the server with only a connection string, so the 23
  Atlas/atlas-local tools did not load. Performance Advisor *data* additionally requires an
  **M10+** cluster.
- **This matches the handoff:** "`atlas-*` MCP tools (Performance Advisor) are deferred — they
  need an Atlas Service Account + an M10 cluster."
- **To enable later:** create an Atlas Service Account, pass its client id/secret to the MCP
  server, and upgrade `target` to M10. Then re-run this check to confirm `suggestedIndexes`,
  `dropIndexSuggestions`, `slowQueryLogs`, `schemaSuggestions` return data.

## Conclusion

The deterministic core of the demo — Diagnose/Test/Verify (explain, indexes, aggregate,
find, count, schema) — is **fully supported on the current M0 cluster via MCP**. The only
unsupported tools are the two Atlas observability tools, both gated behind M10 + an Atlas
Service Account, exactly as the build plan's risk section anticipated. The fixture-based
Detect path (Phase 1) is unaffected and remains the demo's source of truth.

**Recommended follow-ups (not MVP-blocking):**
1. Decide whether to upgrade `target` to M10 for the demo window to enable real-log Detect +
   Performance Advisor (plan estimated ~$60/mo). If staying on M0, the README should state
   Detect runs on the fixture and Performance Advisor is a documented M10 production feature.
2. If/when M10: create an Atlas Service Account and wire `MDB_MCP_API_CLIENT_ID/SECRET`, then
   re-run `tests/mcp/mcp_smoke.py` to validate the two deferred tools.
