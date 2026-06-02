import asyncio

from agents.demo import run_demo
from controller.backends import FakeBackend
from controller.schemas import Evidence, EvidenceMetrics, PackStatus, Severity


def _evidence(stages, keys):
    return Evidence(
        query={"storeLocation": "Denver"},
        explain_plan={"stage": stages[0]},
        metrics=EvidenceMetrics(
            docs_examined=20, docs_returned=20, millis=1, total_keys_examined=keys, stages=stages
        ),
    )


class _FakeNarrator:
    def narrate(self, pack) -> str:
        return "Blocking sort under index B; the ESR-correct index C removes it."


def test_run_demo_catches_trap_recommends_C_and_narrates():
    # before hinted to B -> blocking SORT (17209 keys); DIAGNOSE-only, no mutation, awaits approval
    backend = FakeBackend([_evidence(("FETCH", "SORT", "IXSCAN"), 17209)])

    pack = asyncio.run(
        run_demo(backend=backend, narrator=_FakeNarrator(), created_at="2026-06-02T00:00:00Z")
    )

    assert pack.status is PackStatus.DIAGNOSED
    assert pack.decision is None
    assert pack.after is None
    assert pack.finding.severity is Severity.HIGH
    assert pack.recommendation.index_spec == (
        ("storeLocation", 1),
        ("saleDate", -1),
        ("customer.age", 1),
    )
    assert pack.narrative and "C" in pack.narrative
    # DIAGNOSE is read-only — no index applied or dropped
    assert backend.applied_indexes == []
    assert backend.dropped_indexes == []


def test_run_demo_without_narrator_leaves_narrative_none():
    backend = FakeBackend([_evidence(("FETCH", "SORT", "IXSCAN"), 17209)])

    pack = asyncio.run(run_demo(backend=backend, created_at="2026-06-02T00:00:00Z"))

    assert pack.narrative is None
    assert pack.status is PackStatus.DIAGNOSED
