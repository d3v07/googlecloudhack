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

from controller.backends import FakeBackend  # noqa: E402
from controller.orchestrator import run_diagnosis  # noqa: E402
from controller.schemas import Evidence, EvidenceMetrics, EvidencePack  # noqa: E402

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
    return asyncio.run(
        run_diagnosis(
            FakeBackend([before]),
            run_id="example-esr-001",
            namespace="sample_supplies.sales_agent_demo",
            created_at="2026-06-01T00:00:00Z",
            query_filter=QUERY_FILTER,
            query_sort=QUERY_SORT,
            limit=20,
        )
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
