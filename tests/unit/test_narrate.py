"""Unit tests for controller/narrate.py — all offline, no Gemini I/O."""

import asyncio

from controller.backends import FakeBackend
from controller.diagnosis import diagnose
from controller.narrate import GeminiNarrator, Narrator, build_narration_prompt
from controller.orchestrator import run_diagnosis
from controller.pack import build_pack, pack_evidence_hash
from controller.phases import Phase
from controller.schemas import (
    Decision,
    DecisionAction,
    Evidence,
    EvidenceMetrics,
    EvidencePack,
    PackStatus,
)

QUERY_FILTER = {"storeLocation": "Denver", "customer.age": {"$gte": 30, "$lte": 50}}
QUERY_SORT = [("saleDate", -1)]
LIMIT = 20
NAMESPACE = "sample_supplies.sales_agent_demo"
RUN_ID = "narrate-test-1"
CREATED_AT = "2026-06-01T00:00:00Z"


def _before_evidence(has_blocking_sort: bool = True, keys_examined: int = 17209) -> Evidence:
    stages = ("FETCH", "SORT", "IXSCAN") if has_blocking_sort else ("FETCH", "IXSCAN")
    return Evidence(
        query={"filter": QUERY_FILTER, "sort": QUERY_SORT, "limit": LIMIT},
        explain_plan={"stage": "FETCH"},
        metrics=EvidenceMetrics(
            docs_examined=20,
            docs_returned=20,
            millis=41.0,
            total_keys_examined=keys_examined,
            stages=stages,
        ),
    )


def _after_evidence(has_blocking_sort: bool = False, keys_examined: int = 20) -> Evidence:
    stages = ("FETCH", "SORT", "IXSCAN") if has_blocking_sort else ("FETCH", "IXSCAN")
    return Evidence(
        query={"filter": QUERY_FILTER, "sort": QUERY_SORT, "limit": LIMIT},
        explain_plan={"stage": "FETCH"},
        metrics=EvidenceMetrics(
            docs_examined=20,
            docs_returned=20,
            millis=2.0,
            total_keys_examined=keys_examined,
            stages=stages,
        ),
    )


def _diagnosed_pack(with_after: bool = False) -> EvidencePack:
    diagnosis = diagnose(
        QUERY_FILTER, QUERY_SORT, has_blocking_sort=True, current_index="esr_wrong_B"
    )
    before = _before_evidence()
    if not with_after:
        return build_pack(
            run_id=RUN_ID,
            namespace=NAMESPACE,
            created_at=CREATED_AT,
            before=before,
            finding=diagnosis.finding,
            recommendation=diagnosis.recommendation,
            status=PackStatus.DIAGNOSED,
        )
    # a VERIFIED pack is post-approval: it carries an approve decision + after-evidence
    eh = pack_evidence_hash(before, diagnosis.recommendation)
    return build_pack(
        run_id=RUN_ID,
        namespace=NAMESPACE,
        created_at=CREATED_AT,
        before=before,
        finding=diagnosis.finding,
        recommendation=diagnosis.recommendation,
        status=PackStatus.VERIFIED,
        after=_after_evidence(),
        decision=Decision(action=DecisionAction.APPROVE, evidence_hash=eh, phase=Phase.APPROVE),
    )


class FakeNarrator:
    def narrate(self, pack: EvidencePack) -> str:
        return "fake narrative"


def test_narrator_protocol_structural_subtype():
    narrator: Narrator = FakeNarrator()
    pack = _diagnosed_pack()
    assert narrator.narrate(pack) == "fake narrative"


def test_prompt_includes_before_keys_examined():
    pack = _diagnosed_pack()
    prompt = build_narration_prompt(pack)
    assert "17209" in prompt


def test_prompt_includes_has_blocking_sort():
    pack = _diagnosed_pack()
    prompt = build_narration_prompt(pack)
    assert "has_blocking_sort: True" in prompt


def test_prompt_includes_index_spec():
    pack = _diagnosed_pack()
    prompt = build_narration_prompt(pack)
    # index_spec fields should appear
    assert "storeLocation" in prompt
    assert "saleDate" in prompt
    assert "customer.age" in prompt


def test_prompt_includes_finding_problem():
    pack = _diagnosed_pack()
    prompt = build_narration_prompt(pack)
    assert pack.finding.problem in prompt


def test_prompt_with_after_includes_after_keys_examined():
    pack = _diagnosed_pack(with_after=True)
    prompt = build_narration_prompt(pack)
    # after keys_examined = 20
    assert "total_keys_examined=20" in prompt


def test_prompt_without_after_says_not_yet_measured():
    pack = _diagnosed_pack(with_after=False)
    prompt = build_narration_prompt(pack)
    assert "not yet measured" in prompt


def test_run_diagnosis_with_narrator_sets_narrative():
    backend = FakeBackend([_before_evidence(has_blocking_sort=True, keys_examined=17000)])

    pack = asyncio.run(
        run_diagnosis(
            backend,
            run_id=RUN_ID,
            namespace=NAMESPACE,
            query_filter=QUERY_FILTER,
            query_sort=QUERY_SORT,
            limit=LIMIT,
            created_at=CREATED_AT,
            narrator=FakeNarrator(),
        )
    )

    assert pack.narrative == "fake narrative"


def test_run_diagnosis_without_narrator_leaves_narrative_none():
    backend = FakeBackend([_before_evidence(has_blocking_sort=True)])

    pack = asyncio.run(
        run_diagnosis(
            backend,
            run_id=RUN_ID,
            namespace=NAMESPACE,
            query_filter=QUERY_FILTER,
            query_sort=QUERY_SORT,
            limit=LIMIT,
            created_at=CREATED_AT,
        )
    )

    assert pack.narrative is None


def test_gemini_narrator_default_model():
    narrator = GeminiNarrator()
    assert narrator._model == "gemini-3-flash-preview"


def test_gemini_narrator_model_from_env(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    narrator = GeminiNarrator()
    assert narrator._model == "gemini-2.5-flash"
