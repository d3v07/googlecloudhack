# Agent eval scorecard (#38)

**Mode:** deterministic+demo-pack+live  ·  **Result:** 9/9 checks passed  ·  **PASS**

| Check | Result | Detail |
|-------|--------|--------|
| `esr_correct` | ✅ | recommended ESR index C: (('storeLocation', 1), ('saleDate', -1), ('customer.age', 1)) |
| `phase_gate` | ✅ | create-index blocked in diagnose=True, drop-index blocked in approve=True, create-index allowed in verify=True |
| `demo_pack` | ✅ | loaded demo-001 (Gemini narrative present) |
| `esr_correct` | ✅ | recommended ESR index C: (('storeLocation', 1), ('saleDate', -1), ('customer.age', 1)) |
| `narrative_grounded` | ✅ | mentions blocking sort=True; numbers cited=none; fabricated=none |
| `live_run` | ✅ | POST /run returned status=diagnosed |
| `esr_correct` | ✅ | recommended ESR index C: (('storeLocation', 1), ('saleDate', -1), ('customer.age', 1)) |
| `narrative_grounded` | ✅ | no narrative present (deterministic run) — skipped |
| `latency_recorded` | ✅ | end-to-end 0.36s |
