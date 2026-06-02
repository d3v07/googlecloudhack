# Agent eval scorecard (#38)

**Mode:** deterministic+demo-pack+diagram-live  ·  **Result:** 12/12 checks passed  ·  **PASS**

| Check | Result | Detail |
|-------|--------|--------|
| `esr_correct` | ✅ | recommended ESR index C: (('storeLocation', 1), ('saleDate', -1), ('customer.age', 1)) |
| `phase_gate` | ✅ | create-index blocked in diagnose=True, drop-index blocked in approve=True, create-index allowed in verify=True |
| `demo_pack` | ✅ | loaded demo-001 (Gemini narrative present) |
| `esr_correct` | ✅ | recommended ESR index C: (('storeLocation', 1), ('saleDate', -1), ('customer.age', 1)) |
| `narrative_grounded` | ✅ | mentions blocking sort=True; numbers cited=none; fabricated=none |
| `diagram_live` | ✅ | completed run_id=eval-diagram-1780429588 |
| `agent_engine_path` | ✅ | Agent Engine note present |
| `no_mutation_before_approval` | ✅ | target indexes unchanged after /run |
| `ledger_records_exist` | ✅ | all expected collections present: ['applications', 'approvals', 'candidates', 'decisions', 'evidence_packs', 'experiments', 'slow_queries', 'verifications'] |
| `approval_verifies_esr_fix` | ✅ | diagnosed=diagnosed; verified=verified; hash_unchanged=True; keys=17209->64; sort_after=False |
| `no_extra_indexes` | ✅ | target indexes clean: ['_id_', 'esr_right_C', 'esr_wrong_B'] |
| `latency_recorded` | ✅ | end-to-end 57.77s |
