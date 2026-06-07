"""Workload execution + capture (user persona) and the DBRE slow-query queue.

POST /workload/query runs a guided, validated, read-only query against the demo collection,
captures its real explain evidence, persists an attributed record to `query_log`, and returns a
result preview. GET /workload/slow-queries serves the evidence-ranked triage queue to the DBRE.
Every workload query is attributed to the authenticated user; only the `user` role can run them.
"""

from datetime import datetime, timezone
from typing import Annotated, Protocol
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import ROLE_DBRE, ROLE_USER, require_role
from controller.auth import Identity
from controller.explain import capture_evidence
from controller.workload import (
    DEFAULT_MAX_TIME_MS,
    PRESET_BY_KEY,
    PRESETS,
    QuerySpec,
    WorkloadSpecError,
    build_capture_record,
    build_query,
)

PREVIEW_MAX = 8
SLOW_QUEUE_LIMIT = 100


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def public_record(record: dict) -> dict:
    """Rename the internal _id to captured_id for API responses."""
    out = {key: value for key, value in record.items() if key != "_id"}
    out["captured_id"] = record["_id"]
    return out


class WorkloadService(Protocol):
    def run_query(
        self, spec: QuerySpec, *, username: str, display_name: str, preset: str | None
    ) -> dict: ...
    def list_slow_queries(self) -> list[dict]: ...
    def get_captured(self, captured_id: str) -> dict | None: ...


class MongoWorkloadService:
    def __init__(self, target_collection, query_log_collection) -> None:
        self._target = target_collection
        self._log = query_log_collection

    def run_query(self, spec, *, username, display_name, preset=None) -> dict:
        query_filter, query_sort, limit = build_query(spec)
        evidence = capture_evidence(
            self._target, query_filter, query_sort, limit, max_time_ms=DEFAULT_MAX_TIME_MS
        )
        record = build_capture_record(
            captured_id=uuid4().hex,
            username=username,
            display_name=display_name,
            spec=spec,
            evidence=evidence,
            captured_at=_now_iso(),
            preset=preset,
        )
        self._log.insert_one(dict(record))
        return {
            "captured": public_record(record),
            "preview": self._preview(query_filter, query_sort, limit),
        }

    def _preview(self, query_filter, query_sort, limit) -> list[dict]:
        cursor = self._target.find(
            dict(query_filter),
            projection={
                "_id": False,
                "storeLocation": True,
                "saleDate": True,
                "customer.age": True,
                "purchaseMethod": True,
            },
            sort=list(query_sort) or None,
            limit=min(limit, PREVIEW_MAX),
        ).max_time_ms(DEFAULT_MAX_TIME_MS)
        rows = []
        for doc in cursor:
            sale = doc.get("saleDate")
            rows.append(
                {
                    "storeLocation": doc.get("storeLocation"),
                    "saleDate": sale.isoformat() if hasattr(sale, "isoformat") else sale,
                    "age": (doc.get("customer") or {}).get("age"),
                    "purchaseMethod": doc.get("purchaseMethod"),
                }
            )
        return rows

    def list_slow_queries(self) -> list[dict]:
        # Rank + cap in Mongo (bounded memory + maxTimeMS) rather than loading the whole log.
        records = (
            self._log.find({"signal.is_slow": True})
            .sort("signal.score", -1)
            .limit(SLOW_QUEUE_LIMIT)
            .max_time_ms(DEFAULT_MAX_TIME_MS)
        )
        return [public_record(r) for r in records]

    def get_captured(self, captured_id: str) -> dict | None:
        return self._log.find_one({"_id": captured_id})


def get_workload_service() -> WorkloadService:
    raise HTTPException(status_code=503, detail="workload service is not configured")


def get_workload_service_optional() -> WorkloadService | None:
    """Like get_workload_service but returns None instead of 503 when unconfigured, so /run can
    resolve it eagerly and only fail when a captured_query_id is actually supplied."""
    return None


WorkloadServiceDep = Annotated[WorkloadService, Depends(get_workload_service)]

workload_router = APIRouter()


class WorkloadQueryRequest(BaseModel):
    preset: str | None = None
    store_location: str | None = None
    purchase_method: str | None = None
    age_min: int | None = None
    age_max: int | None = None
    sort_field: str | None = None
    sort_dir: int = -1
    limit: int = 20


@workload_router.get("/workload/presets")
def list_presets(_: Annotated[Identity, Depends(require_role())]) -> list[dict]:
    return [{"key": p.key, "label": p.label, "intent": p.intent} for p in PRESETS]


@workload_router.post("/workload/query")
def run_workload_query(
    body: WorkloadQueryRequest,
    identity: Annotated[Identity, Depends(require_role(ROLE_USER))],
    service: WorkloadServiceDep,
) -> dict:
    if body.preset is not None:
        preset = PRESET_BY_KEY.get(body.preset)
        if preset is None:
            raise HTTPException(status_code=404, detail=f"unknown preset: {body.preset}")
        spec, preset_key = preset.spec, preset.key
    else:
        spec = QuerySpec(
            store_location=body.store_location,
            purchase_method=body.purchase_method,
            age_min=body.age_min,
            age_max=body.age_max,
            sort_field=body.sort_field,
            sort_dir=body.sort_dir,
            limit=body.limit,
        )
        preset_key = None
    try:
        return service.run_query(
            spec, username=identity.username, display_name=identity.display_name, preset=preset_key
        )
    except WorkloadSpecError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@workload_router.get("/workload/slow-queries")
def list_slow_queries(
    _: Annotated[Identity, Depends(require_role(ROLE_DBRE))],
    service: WorkloadServiceDep,
) -> list[dict]:
    return service.list_slow_queries()
