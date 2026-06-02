"""Live #40 demo: the orchestrator hints the obvious index B, so against the live fixture
the agent CATCHES the trap (severity HIGH) and emits a DIAGNOSED pack awaiting human
approval — it does NOT mutate. The fix is applied only when a human approves via the API
(covered by test_e2e). Skips without a Mongo connection string. No narrator here (no Gemini
cost) — narration is exercised separately via `agents/demo.py main()`.
"""

import asyncio

import pytest

from agents.demo import run_demo
from controller.explain import get_connection_string
from controller.schemas import PackStatus, Severity

pytestmark = pytest.mark.skipif(
    get_connection_string() is None, reason="no Mongo connection string in env"
)


def test_live_demo_catches_the_trap_and_awaits_approval():
    pack = asyncio.run(run_demo(get_connection_string(), run_id="demo-live"))

    assert pack.finding.severity is Severity.HIGH
    assert pack.status is PackStatus.DIAGNOSED  # diagnose-only — no auto-fix
    assert pack.decision is None
    assert pack.after is None
    assert pack.before.metrics.has_blocking_sort is True
    assert pack.recommendation.index_spec == (
        ("storeLocation", 1),
        ("saleDate", -1),
        ("customer.age", 1),
    )
