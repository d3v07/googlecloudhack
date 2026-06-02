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
        return Check("narrative_grounded", True, "no narrative present (deterministic run) — skipped")

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
