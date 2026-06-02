"""Grading logic for the agent eval (#38) — pure, offline-testable.

Four dimensions, each a `Check` with a pass/fail and a human-readable detail:

  1. esr_correct       — recommends the ESR index C (Equality, Sort, Range),
                         NOT the obvious-but-wrong B (Equality, Range, Sort).
  2. narrative_grounded— the agent's narrative cites the REAL evidence (the
                         blocking sort + the actual keys-examined figures) and
                         invents no other numbers. Catches hallucination.
  3. phase_gate        — a write tool (create-index/drop-index) is blocked
                         outside the verify phase.
  4. latency_recorded  — end-to-end wall time was captured (graded live only).

The grader takes already-computed inputs so it can be unit-tested with no DB,
no model, and no network.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from agents.gating import is_allowed
from controller.phases import Phase

# The fixture's correct (C) and wrong (B) index orders — the contract from #9.
ESR_CORRECT_C: tuple[tuple[str, int], ...] = (
    ("storeLocation", 1),
    ("saleDate", -1),
    ("customer.age", 1),
)
OBVIOUS_WRONG_B: tuple[tuple[str, int], ...] = (
    ("storeLocation", 1),
    ("customer.age", 1),
    ("saleDate", -1),
)

# Real fixture numbers the narrative is allowed to cite (the only legitimate
# figures). Any *other* multi-digit number in the narrative is treated as
# potentially fabricated.
REAL_KEYS_B = 17209
REAL_KEYS_C = 64
EXPECTED_LEDGER_COLLECTIONS = {
    "slow_queries",
    "candidates",
    "experiments",
    "decisions",
    "evidence_packs",
    "approvals",
    "applications",
    "verifications",
}
EXPECTED_TARGET_INDEXES = {"_id_", "esr_wrong_B", "esr_right_C"}


@dataclass
class Check:
    name: str
    passed: bool
    detail: str


@dataclass
class Scorecard:
    checks: list[Check] = field(default_factory=list)

    def add(self, name: str, passed: bool, detail: str) -> None:
        self.checks.append(Check(name, passed, detail))

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def summary(self) -> str:
        n_pass = sum(1 for c in self.checks if c.passed)
        return f"{n_pass}/{len(self.checks)} checks passed"


def _normalize_spec(spec) -> tuple[tuple[str, int], ...]:
    """Coerce a recommendation index_spec (list-of-lists or tuple-of-tuples) to a
    comparable tuple-of-tuples."""
    return tuple((str(f), int(d)) for f, d in spec)


def grade_esr_correct(index_spec) -> Check:
    got = _normalize_spec(index_spec)
    if got == ESR_CORRECT_C:
        return Check("esr_correct", True, f"recommended ESR index C: {got}")
    if got == OBVIOUS_WRONG_B:
        return Check("esr_correct", False, f"fell for the obvious WRONG index B: {got}")
    return Check("esr_correct", False, f"unexpected index spec: {got}")


def grade_phase_gate() -> Check:
    """A write must be blocked in diagnose/approve and allowed only in verify."""
    blocked_in_diagnose = not is_allowed(Phase.DIAGNOSE, "create-index")
    blocked_in_approve = not is_allowed(Phase.APPROVE, "drop-index")
    allowed_in_verify = is_allowed(Phase.VERIFY, "create-index")
    ok = blocked_in_diagnose and blocked_in_approve and allowed_in_verify
    detail = (
        f"create-index blocked in diagnose={blocked_in_diagnose}, "
        f"drop-index blocked in approve={blocked_in_approve}, "
        f"create-index allowed in verify={allowed_in_verify}"
    )
    return Check("phase_gate", ok, detail)


_NUM = re.compile(r"\d[\d,]{2,}")  # 3+ digit runs (allowing thousands commas)


def grade_narrative_grounded(narrative: str | None) -> Check:
    """The narrative must reference the blocking sort and may only cite the real
    fixture figures — any other large number is treated as fabricated."""
    if not narrative:
        # /run packs are deterministic-only (no narrative). That's not a failure
        # of grounding — there's simply nothing to ground. Mark as skipped-pass
        # with a clear detail so the scorecard is honest.
        return Check(
            "narrative_grounded", True, "no narrative present (deterministic run) — skipped"
        )

    text = narrative.lower()
    mentions_sort = "sort" in text and ("block" in text or "in-memory" in text or "memory" in text)

    cited = {int(m.group().replace(",", "")) for m in _NUM.finditer(narrative)}
    allowed = {REAL_KEYS_B, REAL_KEYS_C}
    fabricated = {n for n in cited if n not in allowed}

    ok = mentions_sort and not fabricated
    detail = (
        f"mentions blocking sort={mentions_sort}; "
        f"numbers cited={sorted(cited) or 'none'}; "
        f"fabricated={sorted(fabricated) or 'none'}"
    )
    return Check("narrative_grounded", ok, detail)


def grade_latency(elapsed_s: float | None) -> Check:
    if elapsed_s is None:
        return Check("latency_recorded", False, "no latency captured")
    return Check("latency_recorded", True, f"end-to-end {elapsed_s:.2f}s")


def grade_agent_engine_used(pack: dict) -> Check:
    notes = [
        str(item.get("note", "")) for item in pack.get("phase_log", []) if isinstance(item, dict)
    ]
    used = any("agent_engine=" in note for note in notes)
    detail = "Agent Engine note present" if used else "Agent Engine note missing from phase_log"
    return Check("agent_engine_path", used, detail)


def grade_no_mutation_before_approval(
    before_indexes: set[str], after_run_indexes: set[str]
) -> Check:
    ok = before_indexes == after_run_indexes
    detail = (
        f"before={sorted(before_indexes)}; after_run={sorted(after_run_indexes)}"
        if not ok
        else "target indexes unchanged after /run"
    )
    return Check("no_mutation_before_approval", ok, detail)


def grade_ledger_records(collections_present: set[str]) -> Check:
    missing = EXPECTED_LEDGER_COLLECTIONS - collections_present
    ok = not missing
    detail = (
        f"all expected collections present: {sorted(collections_present)}"
        if ok
        else f"missing ledger collections: {sorted(missing)}"
    )
    return Check("ledger_records_exist", ok, detail)


def grade_approval_verified(diagnosed_pack: dict, verified_pack: dict) -> Check:
    before_keys = diagnosed_pack.get("before", {}).get("metrics", {}).get("total_keys_examined")
    after_metrics = verified_pack.get("after", {}).get("metrics", {})
    after_keys = after_metrics.get("total_keys_examined")
    ok = (
        diagnosed_pack.get("status") == "diagnosed"
        and verified_pack.get("status") == "verified"
        and diagnosed_pack.get("evidence_hash") == verified_pack.get("evidence_hash")
        and after_metrics.get("has_blocking_sort") is False
        and isinstance(before_keys, int | float)
        and isinstance(after_keys, int | float)
        and after_keys < before_keys
    )
    detail = (
        f"diagnosed={diagnosed_pack.get('status')}; verified={verified_pack.get('status')}; "
        f"hash_unchanged={diagnosed_pack.get('evidence_hash') == verified_pack.get('evidence_hash')}; "
        f"keys={before_keys}->{after_keys}; sort_after={after_metrics.get('has_blocking_sort')}"
    )
    return Check("approval_verifies_esr_fix", ok, detail)


def grade_no_extra_indexes(indexes: set[str]) -> Check:
    extra = indexes - EXPECTED_TARGET_INDEXES
    ok = not extra
    detail = (
        f"target indexes clean: {sorted(indexes)}"
        if ok
        else f"unexpected indexes left behind: {sorted(extra)}"
    )
    return Check("no_extra_indexes", ok, detail)
