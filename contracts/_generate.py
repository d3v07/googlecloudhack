"""Regenerate the EvidencePack JSON Schema + example pack from the pydantic model
(the single source of truth). Run: uv run python contracts/_generate.py

The contract test asserts the committed schema stays in sync with the model, so run
this whenever EvidencePack changes.
"""

import json
from pathlib import Path

from controller.diagnosis import diagnose
from controller.pack import build_pack
from controller.schemas import Evidence, EvidenceMetrics, EvidencePack, PackStatus

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
    diagnosis = diagnose(
        QUERY_FILTER, QUERY_SORT, has_blocking_sort=True, current_index="esr_wrong_B"
    )
    return build_pack(
        run_id="example-esr-001",
        namespace="sample_supplies.sales_agent_demo",
        created_at="2026-06-01T00:00:00Z",
        before=before,
        finding=diagnosis.finding,
        recommendation=diagnosis.recommendation,
        status=PackStatus.DIAGNOSED,
    )


def main() -> None:
    (HERE / "evidence_pack.schema.json").write_text(
        json.dumps(EvidencePack.model_json_schema(), indent=2, sort_keys=True) + "\n"
    )
    examples = HERE / "examples"
    examples.mkdir(exist_ok=True)
    (examples / "evidence_pack.example.json").write_text(
        json.dumps(_example_pack().model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    )
    print("regenerated contracts/evidence_pack.schema.json + examples/evidence_pack.example.json")


if __name__ == "__main__":
    main()
