"""Regenerate the EvidencePack JSON Schema + example pack from the pydantic model
(the single source of truth). Run: uv run python contracts/_generate.py

The contract test asserts the committed schema stays in sync with the model, so run
this whenever EvidencePack changes.
"""

import json
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from controller.orchestrator import AgentDiagnosisResult, run_agent_diagnosis  # noqa: E402
from controller.schemas import (  # noqa: E402
    AgentTraceActor,
    AgentTraceEvent,
    AgentTraceStage,
    AgentTraceStatus,
    Evidence,
    EvidenceMetrics,
    EvidencePack,
)

HERE = Path(__file__).parent
QUERY_FILTER = {"storeLocation": "Denver", "customer.age": {"$gte": 30, "$lte": 50}}
QUERY_SORT = [("saleDate", -1)]


def _example_pack() -> EvidencePack:
    before = Evidence(
        query={"filter": QUERY_FILTER, "sort": QUERY_SORT, "limit": 20},
        explain_plan={
            "stage": "FETCH",
            "inputStage": {
                "stage": "SORT",
                "inputStage": {"stage": "IXSCAN", "indexName": "esr_wrong_B"},
            },
        },
        metrics=EvidenceMetrics(
            docs_examined=20,
            docs_returned=20,
            millis=41,
            total_keys_examined=17209,
            stages=("FETCH", "SORT", "IXSCAN"),
        ),
    )

    class _ExampleAgent:
        async def diagnose(
            self,
            *,
            run_id: str,
            namespace: str,
            query_filter: dict,
            query_sort: list[tuple[str, int]],
            limit: int,
        ) -> AgentDiagnosisResult:
            del run_id, namespace, query_filter, query_sort, limit
            return AgentDiagnosisResult(
                source="example_agent_engine",
                before=before,
                narrative="",
                proposed_index=(("storeLocation", 1), ("saleDate", -1), ("customer.age", 1)),
                trace=(
                    AgentTraceEvent(
                        stage=AgentTraceStage.DETECT,
                        actor=AgentTraceActor.AGENT_ENGINE,
                        status=AgentTraceStatus.OK,
                        summary="Agent Engine captured slow-query explain evidence.",
                        component="diagnose_agent",
                        resource="projects/example/locations/us-central1/reasoningEngines/diagnose",
                        tool="explain_slow_query",
                    ),
                    AgentTraceEvent(
                        stage=AgentTraceStage.CANDIDATE,
                        actor=AgentTraceActor.AGENT_ENGINE,
                        status=AgentTraceStatus.OK,
                        summary="Agent Engine compared candidates and selected esr_right_C.",
                        component="candidate_agent",
                        resource="projects/example/locations/us-central1/reasoningEngines/candidate",
                        tool="compare_candidate_indexes",
                    ),
                    AgentTraceEvent(
                        stage=AgentTraceStage.DIAGNOSE,
                        actor=AgentTraceActor.AGENT_ENGINE,
                        status=AgentTraceStatus.OK,
                        summary="Agent Engine ran diagnose_candidate.",
                        component="diagnose_agent",
                        resource="projects/example/locations/us-central1/reasoningEngines/diagnose",
                        tool="diagnose_candidate",
                    ),
                    AgentTraceEvent(
                        stage=AgentTraceStage.RATIONALE,
                        actor=AgentTraceActor.AGENT_ENGINE,
                        status=AgentTraceStatus.OK,
                        summary="Agent Engine produced an evidence-grounded rationale.",
                        component="rationale_agent",
                        resource="projects/example/locations/us-central1/reasoningEngines/rationale",
                        tool="rationalize_recommendation",
                    ),
                ),
            )

    pack = asyncio.run(
        run_agent_diagnosis(
            _ExampleAgent(),
            run_id="example-esr-001",
            namespace="sample_supplies.sales_agent_demo",
            created_at="2026-06-01T00:00:00Z",
            query_filter=QUERY_FILTER,
            query_sort=QUERY_SORT,
            limit=20,
        )
    )
    return pack.model_copy(update={"narrative": None})


def main() -> None:
    pack_json = json.dumps(_example_pack().model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    (HERE / "evidence_pack.schema.json").write_text(
        json.dumps(EvidencePack.model_json_schema(), indent=2, sort_keys=True) + "\n"
    )
    examples = HERE / "examples"
    examples.mkdir(exist_ok=True)
    (examples / "evidence_pack.example.json").write_text(pack_json)
    (ROOT / "dashboard/lib/example_pack.json").write_text(pack_json)
    print(
        "regenerated contracts/evidence_pack.schema.json, "
        "examples/evidence_pack.example.json, and dashboard/lib/example_pack.json"
    )


if __name__ == "__main__":
    main()
