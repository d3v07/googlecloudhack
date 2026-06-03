# Agent eval scorecard (#38)

**Mode:** deterministic  ·  **Result:** 2/2 checks passed  ·  **PASS**

| Check | Result | Detail |
|-------|--------|--------|
| `esr_correct` | ✅ | recommended ESR index C: (('storeLocation', 1), ('saleDate', -1), ('customer.age', 1)) |
| `phase_gate` | ✅ | create-index blocked in diagnose=True, drop-index blocked in approve=True, create-index allowed in verify=True |
