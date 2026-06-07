import types

import pytest
from fastapi.testclient import TestClient

from api.server import create_app
from controller.auth import Identity, make_session_token
from controller.schemas import EvidenceMetrics
from controller.workload import (
    MAX_LIMIT,
    PRESETS,
    QuerySpec,
    WorkloadSpecError,
    assert_safe_query,
    build_capture_record,
    build_query,
    slow_signal,
)

SECRET = "wl-secret"


# ---------------------------------------------------------------- build_query / validate


def test_build_query_full_trap_spec() -> None:
    f, s, lim = build_query(QuerySpec("Denver", None, 30, 50, "saleDate", -1, 20))
    assert f == {"storeLocation": "Denver", "customer.age": {"$gte": 30, "$lte": 50}}
    assert s == [("saleDate", -1)]
    assert lim == 20


def test_build_query_healthy_no_sort() -> None:
    f, s, lim = build_query(QuerySpec("London", None, None, None, None, -1, 25))
    assert f == {"storeLocation": "London"}
    assert s == []


def test_build_query_method_and_one_sided_age() -> None:
    f, s, _ = build_query(QuerySpec(None, "Online", 18, None, "customer.age", 1, 10))
    assert f == {"purchaseMethod": "Online", "customer.age": {"$gte": 18}}
    assert s == [("customer.age", 1)]


def test_assert_safe_query_accepts_valid() -> None:
    assert_safe_query(
        {"storeLocation": "Denver", "customer.age": {"$gte": 30, "$lte": 50}}, [("saleDate", -1)]
    )


@pytest.mark.parametrize(
    "bad_filter",
    [
        {"$where": "true"},
        {"storeLocation": {"$ne": "x"}},
        {"customer.age": {"$where": "1"}},
        {"customer.age": "not-a-range"},
        {"unknownField": "x"},
    ],
)
def test_assert_safe_query_rejects_filter(bad_filter: dict) -> None:
    with pytest.raises(WorkloadSpecError):
        assert_safe_query(bad_filter, [])


def test_assert_safe_query_rejects_bad_sort() -> None:
    with pytest.raises(WorkloadSpecError):
        assert_safe_query({}, [("totalAmount", -1)])


@pytest.mark.parametrize(
    "bad_age",
    [
        {"customer.age": {"$gte": 10}},  # below 16
        {"customer.age": {"$lte": 99}},  # above 75
        {"customer.age": {"$gte": "30"}},  # string, not int
        {"customer.age": {"$gte": True}},  # bool masquerading as int
    ],
)
def test_assert_safe_query_rejects_age_value_shape(bad_age: dict) -> None:
    with pytest.raises(WorkloadSpecError):
        assert_safe_query(bad_age, [])


@pytest.mark.parametrize(
    "spec",
    [
        QuerySpec(store_location="Mars"),
        QuerySpec(purchase_method="Telepathy"),
        QuerySpec(age_min=10),
        QuerySpec(age_max=99),
        QuerySpec(age_min=50, age_max=40),
        QuerySpec(sort_field="totalAmount"),
        QuerySpec(sort_dir=2),
        QuerySpec(limit=0),
        QuerySpec(limit=MAX_LIMIT + 1),
    ],
)
def test_validate_spec_rejects(spec: QuerySpec) -> None:
    with pytest.raises(WorkloadSpecError):
        build_query(spec)


# ---------------------------------------------------------------- slow_signal


def _metrics(docs_examined: int, docs_returned: int, keys: int, stages: tuple) -> EvidenceMetrics:
    return EvidenceMetrics(
        docs_examined=docs_examined,
        docs_returned=docs_returned,
        millis=1.0,
        total_keys_examined=keys,
        stages=stages,
    )


def test_slow_signal_blocking_sort_high_slow() -> None:
    sig = slow_signal(_metrics(50000, 20, 50000, ("IXSCAN", "FETCH", "SORT")))
    assert sig.blocking_sort and sig.is_slow and sig.severity == "high"


def test_slow_signal_collscan_high_slow() -> None:
    sig = slow_signal(_metrics(300000, 20, 0, ("COLLSCAN",)))
    assert sig.collscan and sig.is_slow and sig.severity == "high"


def test_slow_signal_high_ratio_no_sort_is_slow() -> None:
    sig = slow_signal(_metrics(10000, 100, 10000, ("IXSCAN", "FETCH")))
    assert sig.is_slow and not sig.blocking_sort


def test_slow_signal_healthy_not_slow() -> None:
    sig = slow_signal(_metrics(10, 10, 10, ("IXSCAN", "FETCH")))
    assert not sig.is_slow and sig.severity == "low"


def test_slow_signal_ranks_sort_over_collscan_over_ratio() -> None:
    blocking = slow_signal(_metrics(50000, 20, 50000, ("IXSCAN", "SORT")))
    collscan = slow_signal(_metrics(300000, 20, 0, ("COLLSCAN",)))
    ratio = slow_signal(_metrics(10000, 100, 10000, ("IXSCAN", "FETCH")))
    assert blocking.score > collscan.score > ratio.score


# ---------------------------------------------------------------- build_capture_record


def test_build_capture_record_shape() -> None:
    evidence = types.SimpleNamespace(metrics=_metrics(50000, 20, 50000, ("IXSCAN", "SORT")))
    rec = build_capture_record(
        captured_id="cap1",
        username="dev.trivedi",
        display_name="Dev Trivedi",
        spec=QuerySpec("Denver", None, 30, 50, "saleDate", -1, 20),
        evidence=evidence,
        captured_at="2026-06-07T00:00:00Z",
        preset="denver_recent",
    )
    assert rec["_id"] == "cap1"
    assert rec["user"] == {"username": "dev.trivedi", "display_name": "Dev Trivedi"}
    assert rec["preset"] == "denver_recent"
    assert rec["query"]["sort"] == [["saleDate", -1]]
    assert rec["signal"]["is_slow"] is True
    assert rec["metrics"]["has_blocking_sort"] is True


# ---------------------------------------------------------------- routes


class FakeWorkload:
    def __init__(self) -> None:
        self.runs: list = []

    def run_query(self, spec, *, username, display_name, preset) -> dict:
        self.runs.append((spec, username, preset))
        return {
            "captured": {
                "captured_id": "cap1",
                "user": {"username": username, "display_name": display_name},
                "preset": preset,
                "signal": {"is_slow": True},
            },
            "preview": [{"storeLocation": "Denver"}],
        }

    def list_slow_queries(self) -> list[dict]:
        return [{"captured_id": "cap1", "signal": {"is_slow": True, "score": 1.0}}]

    def get_captured(self, captured_id):
        return None


class RaisingWorkload(FakeWorkload):
    def run_query(self, spec, **kwargs) -> dict:
        raise WorkloadSpecError("bad spec")


def _client(monkeypatch, workload) -> TestClient:
    monkeypatch.setenv("SESSION_SECRET", SECRET)
    monkeypatch.delenv("MONGO_SECRET_NAME", raising=False)
    monkeypatch.setenv("PACKS_DIR", "/tmp/nonexistent_gcrah_workload_test_xyz")
    return TestClient(create_app(workload_service=workload))


def _auth(role: str, username: str = "u", name: str = "U") -> dict:
    return {"Authorization": f"Bearer {make_session_token(Identity(username, name, role), SECRET)}"}


def test_run_query_preset_attributed(monkeypatch) -> None:
    wl = FakeWorkload()
    resp = _client(monkeypatch, wl).post(
        "/workload/query",
        json={"preset": "denver_recent"},
        headers=_auth("user", username="dev.trivedi", name="Dev Trivedi"),
    )
    assert resp.status_code == 200
    assert resp.json()["captured"]["captured_id"] == "cap1"
    assert wl.runs[0][1] == "dev.trivedi" and wl.runs[0][2] == "denver_recent"


def test_run_query_custom_spec(monkeypatch) -> None:
    wl = FakeWorkload()
    resp = _client(monkeypatch, wl).post(
        "/workload/query",
        json={"store_location": "Seattle", "age_min": 25, "age_max": 45, "sort_field": "saleDate"},
        headers=_auth("user"),
    )
    assert resp.status_code == 200
    spec = wl.runs[0][0]
    assert spec.store_location == "Seattle" and spec.sort_field == "saleDate"


def test_run_query_unknown_preset_404(monkeypatch) -> None:
    resp = _client(monkeypatch, FakeWorkload()).post(
        "/workload/query", json={"preset": "nope"}, headers=_auth("user")
    )
    assert resp.status_code == 404


def test_run_query_invalid_spec_422(monkeypatch) -> None:
    resp = _client(monkeypatch, RaisingWorkload()).post(
        "/workload/query", json={"store_location": "Denver"}, headers=_auth("user")
    )
    assert resp.status_code == 422


def test_run_query_requires_user_role(monkeypatch) -> None:
    client = _client(monkeypatch, FakeWorkload())
    assert (
        client.post(
            "/workload/query", json={"preset": "denver_recent"}, headers=_auth("dbre")
        ).status_code
        == 403
    )
    assert client.post("/workload/query", json={"preset": "denver_recent"}).status_code == 401


def test_presets_endpoint(monkeypatch) -> None:
    resp = _client(monkeypatch, FakeWorkload()).get("/workload/presets", headers=_auth("user"))
    assert resp.status_code == 200
    assert {p["key"] for p in resp.json()} >= {"denver_recent", "london_browse"}
    assert len(resp.json()) == len(PRESETS)


def test_slow_queries_requires_dbre(monkeypatch) -> None:
    client = _client(monkeypatch, FakeWorkload())
    assert client.get("/workload/slow-queries", headers=_auth("user")).status_code == 403
    resp = client.get("/workload/slow-queries", headers=_auth("dbre"))
    assert resp.status_code == 200
    assert resp.json()[0]["captured_id"] == "cap1"
