# Agent eval scorecard (#38)

**Mode:** deterministic+demo-pack+live+diagram-live  ·  **Result:** 20/20 checks passed  ·  **PASS**

| Check | Result | Detail |
|-------|--------|--------|
| `esr_correct` | ✅ | recommended ESR index C: (('storeLocation', 1), ('saleDate', -1), ('customer.age', 1)) |
| `phase_gate` | ✅ | create-index blocked in diagnose=True, drop-index blocked in approve=True, create-index allowed in verify=True |
| `demo_pack` | ✅ | loaded demo-001 (Gemini narrative present) |
| `demo_pack_esr_correct` | ✅ | recommended ESR index C: (('storeLocation', 1), ('saleDate', -1), ('customer.age', 1)) |
| `demo_pack_narrative_grounded` | ✅ | mentions blocking sort=True; numbers cited=[17209]; fabricated=none |
| `live_run` | ✅ | POST /run returned status=diagnosed |
| `live_agent_engine_path` | ✅ | Agent Engine tool trace present: ['compare_candidate_indexes', 'diagnose_candidate', 'explain_slow_query', 'rationalize_recommendation'] |
| `live_esr_correct` | ✅ | recommended ESR index C: (('storeLocation', 1), ('saleDate', -1), ('customer.age', 1)) |
| `live_narrative_grounded` | ✅ | mentions blocking sort=True; numbers cited=[17209]; fabricated=none |
| `live_latency` | ✅ | end-to-end 25.97s |
| `diagram_live` | ✅ | completed run_id=eval-diagram-1780505191 |
| `approval_gate_first` | ✅ | first trace event is approval_gate/gate and gate is pending on the pack hash |
| `agent_engine_path` | ✅ | Agent Engine tool trace present: ['compare_candidate_indexes', 'diagnose_candidate', 'explain_slow_query', 'rationalize_recommendation'] |
| `no_mutation_before_approval` | ✅ | target indexes unchanged after /run |
| `approval_gate_ledger_records` | ✅ | gate-opened and gate-pending ledger records exist |
| `ledger_records_exist` | ✅ | all expected collections present with Agent Engine sources: ['applications', 'approvals', 'candidates', 'decisions', 'evidence_packs', 'experiments', 'slow_queries', 'verifications'] |
| `approval_verifies_esr_fix` | ✅ | diagnosed=diagnosed; verified=verified; hash_unchanged=True; keys=17209->64; sort_after=False |
| `no_extra_indexes` | ✅ | target indexes clean: ['_id_', 'esr_right_C', 'esr_wrong_B'] |
| `tokenless_writes_rejected` | ✅ | POST /run=401; POST /decision=401 |
| `latency` | ✅ | end-to-end 22.87s |
