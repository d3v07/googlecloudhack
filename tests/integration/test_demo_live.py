"""Live #40 demo: the orchestrator hints the obvious index B, so against the live
fixture the agent CATCHES the trap (severity HIGH) and verifies the C fix. Skips
without a Mongo connection string. No narrator here (no Gemini cost) — narration is
exercised separately via `agents/demo.py main()`.
"""

import asyncio

import pytest

from agents.demo import run_demo
from controller.explain import get_connection_string
from controller.schemas import PackStatus, Severity

pytestmark = pytest.mark.skipif(
    get_connection_string() is None, reason="no Mongo connection string in env"
)


def test_live_demo_catches_and_fixes_the_trap():
    pack = asyncio.run(run_demo(get_connection_string(), run_id="demo-live"))

    assert pack.finding.severity is Severity.HIGH
    assert pack.status is PackStatus.VERIFIED
    assert pack.before.metrics.has_blocking_sort is True
    assert pack.after is not None and pack.after.metrics.has_blocking_sort is False
    assert pack.before.metrics.total_keys_examined > pack.after.metrics.total_keys_examined
