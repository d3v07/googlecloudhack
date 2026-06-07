"""Guided workload query contract + evidence-based slow-query ranking.

Pure and offline-testable. The query a user can run is built ONLY from validated parameters —
equality on storeLocation/purchaseMethod, a customer.age range, a sort on saleDate/customer.age,
and a capped limit — never a raw Mongo filter. That keeps every workload query injection-safe
and strictly read-only. ESR-trap presets force a blocking in-memory SORT against the baseline
index set ({storeLocation:1} + {purchaseMethod:1}); healthy presets are served in index order.
Ranking is by explain evidence (blocking sort, COLLSCAN, docs-examined/returned ratio, keys),
never wall-clock time, which is noisy on shared clusters.
"""

from dataclasses import dataclass

NAMESPACE_DB = "sample_supplies"
NAMESPACE_COLL = "sales_agent_demo"
NAMESPACE = f"{NAMESPACE_DB}.{NAMESPACE_COLL}"

STORE_LOCATIONS = ("Austin", "Denver", "London", "New York", "San Diego", "Seattle")
PURCHASE_METHODS = ("In store", "Online", "Phone")
SORT_FIELDS = ("saleDate", "customer.age")
AGE_MIN, AGE_MAX = 16, 75
MAX_LIMIT = 200
DEFAULT_MAX_TIME_MS = 5000

# docs examined per doc returned above which a sort-free query is still "slow" (over-scan)
SLOW_RATIO = 25.0

# Baseline index set for the workload demo — equality serving only, NO saleDate ordering, so a
# query that sorts on saleDate is forced into a blocking SORT and the ESR fix is a real change.
BASELINE_INDEXES = (
    ([("storeLocation", 1)], "store_eq"),
    ([("purchaseMethod", 1)], "method_eq"),
)
# Legacy fixture indexes dropped so they can't pre-serve the trap (esr_right_C is the ESR answer).
LEGACY_INDEX_NAMES = ("esr_wrong_B", "esr_right_C")
APPLIED_INDEX_PREFIX = "gcrah_rec_"


class WorkloadSpecError(ValueError):
    """Invalid guided-query parameters — rejected before any database access."""


@dataclass(frozen=True)
class QuerySpec:
    store_location: str | None = None
    purchase_method: str | None = None
    age_min: int | None = None
    age_max: int | None = None
    sort_field: str | None = None
    sort_dir: int = -1
    limit: int = 20


@dataclass(frozen=True)
class Preset:
    key: str
    label: str
    intent: str  # "trap" | "healthy"
    spec: QuerySpec


PRESETS: tuple[Preset, ...] = (
    Preset(
        "denver_recent",
        "Denver buyers 30–50, newest first",
        "trap",
        QuerySpec("Denver", None, 30, 50, "saleDate", -1, 20),
    ),
    Preset(
        "seattle_recent",
        "Seattle buyers 25–45, newest first",
        "trap",
        QuerySpec("Seattle", None, 25, 45, "saleDate", -1, 20),
    ),
    Preset(
        "online_recent",
        "Online orders 18–35, newest first",
        "trap",
        QuerySpec(None, "Online", 18, 35, "saleDate", -1, 25),
    ),
    Preset(
        "austin_oldest",
        "Austin buyers 40–60, oldest first",
        "trap",
        QuerySpec("Austin", None, 40, 60, "saleDate", 1, 20),
    ),
    Preset(
        "phone_seniors",
        "Phone orders 55–75, newest first",
        "trap",
        QuerySpec(None, "Phone", 55, 75, "saleDate", -1, 15),
    ),
    Preset(
        "ny_recent",
        "New York buyers 30–45, newest first",
        "trap",
        QuerySpec("New York", None, 30, 45, "saleDate", -1, 20),
    ),
    Preset(
        "denver_lookup",
        "Denver buyers — lookup, no sort",
        "healthy",
        QuerySpec("Denver", None, None, None, None, -1, 10),
    ),
    Preset(
        "online_lookup",
        "Online orders — lookup, no sort",
        "healthy",
        QuerySpec(None, "Online", None, None, None, -1, 10),
    ),
    Preset(
        "london_browse",
        "London buyers — browse, no sort",
        "healthy",
        QuerySpec("London", None, None, None, None, -1, 25),
    ),
)
PRESET_BY_KEY = {p.key: p for p in PRESETS}


def validate_spec(spec: QuerySpec) -> QuerySpec:
    if spec.store_location is not None and spec.store_location not in STORE_LOCATIONS:
        raise WorkloadSpecError(f"unknown storeLocation: {spec.store_location!r}")
    if spec.purchase_method is not None and spec.purchase_method not in PURCHASE_METHODS:
        raise WorkloadSpecError(f"unknown purchaseMethod: {spec.purchase_method!r}")
    for bound in (spec.age_min, spec.age_max):
        if bound is not None and not (AGE_MIN <= bound <= AGE_MAX):
            raise WorkloadSpecError(f"age out of range [{AGE_MIN},{AGE_MAX}]: {bound}")
    if spec.age_min is not None and spec.age_max is not None and spec.age_min > spec.age_max:
        raise WorkloadSpecError("age_min must be <= age_max")
    if spec.sort_field is not None and spec.sort_field not in SORT_FIELDS:
        raise WorkloadSpecError(f"unsupported sort field: {spec.sort_field!r}")
    if spec.sort_dir not in (1, -1):
        raise WorkloadSpecError("sort_dir must be 1 or -1")
    if not (1 <= spec.limit <= MAX_LIMIT):
        raise WorkloadSpecError(f"limit must be in [1,{MAX_LIMIT}]")
    return spec


def build_query(spec: QuerySpec) -> tuple[dict, list[tuple[str, int]], int]:
    """Validated spec -> (filter, sort, limit). Raises WorkloadSpecError on any bad input."""
    validate_spec(spec)
    query_filter: dict = {}
    if spec.store_location is not None:
        query_filter["storeLocation"] = spec.store_location
    if spec.purchase_method is not None:
        query_filter["purchaseMethod"] = spec.purchase_method
    age: dict = {}
    if spec.age_min is not None:
        age["$gte"] = spec.age_min
    if spec.age_max is not None:
        age["$lte"] = spec.age_max
    if age:
        query_filter["customer.age"] = age
    query_sort = [(spec.sort_field, spec.sort_dir)] if spec.sort_field is not None else []
    return query_filter, query_sort, spec.limit


_ALLOWED_FILTER_KEYS = frozenset({"storeLocation", "purchaseMethod", "customer.age"})
_ALLOWED_RANGE_OPS = frozenset({"$gte", "$lte"})


def assert_safe_query(query_filter: dict, query_sort: list[tuple[str, int]]) -> None:
    """Re-validate a query loaded from query_log before it reaches the backend. query_log is only
    written through the validated run_query path; re-checking here stops a future writer from
    smuggling an operator (e.g. $where) the guided builder could never produce — defense in depth."""
    for key, value in query_filter.items():
        if key not in _ALLOWED_FILTER_KEYS:
            raise WorkloadSpecError(f"disallowed filter field: {key!r}")
        if key == "customer.age":
            if not isinstance(value, dict) or not set(value).issubset(_ALLOWED_RANGE_OPS):
                raise WorkloadSpecError("customer.age must be a {$gte,$lte} range")
            for bound in value.values():
                if (
                    isinstance(bound, bool)
                    or not isinstance(bound, int)
                    or not (AGE_MIN <= bound <= AGE_MAX)
                ):
                    raise WorkloadSpecError(
                        f"customer.age bound out of range [{AGE_MIN},{AGE_MAX}]: {bound!r}"
                    )
        elif not isinstance(value, str):
            raise WorkloadSpecError(f"{key} must be an equality value")
    for field, direction in query_sort:
        if field not in SORT_FIELDS or direction not in (1, -1):
            raise WorkloadSpecError(f"disallowed sort: {field!r}")


@dataclass(frozen=True)
class SlowSignal:
    is_slow: bool
    severity: str  # "high" | "medium" | "low"
    score: float
    ratio: float
    blocking_sort: bool
    collscan: bool


def _ratio(docs_examined: int, docs_returned: int) -> float:
    return docs_examined / max(docs_returned, 1)


def slow_signal(metrics) -> SlowSignal:
    """Evidence-only slowness verdict + a deterministic ranking score. `metrics` is an
    EvidenceMetrics (or any object with docs_examined/docs_returned/total_keys_examined/
    has_blocking_sort/stages)."""
    stages = tuple(metrics.stages)
    collscan = "COLLSCAN" in stages
    blocking_sort = bool(metrics.has_blocking_sort)
    ratio = _ratio(metrics.docs_examined, metrics.docs_returned)
    is_slow = blocking_sort or collscan or ratio >= SLOW_RATIO
    severity = "high" if (blocking_sort or collscan) else ("medium" if ratio >= 10 else "low")
    score = (
        (1_000_000.0 if blocking_sort else 0.0)
        + (500_000.0 if collscan else 0.0)
        + min(ratio, 10_000.0) * 50.0
        + min(float(metrics.total_keys_examined), 1_000_000.0) / 100.0
    )
    return SlowSignal(
        is_slow=is_slow,
        severity=severity,
        score=score,
        ratio=ratio,
        blocking_sort=blocking_sort,
        collscan=collscan,
    )


def build_capture_record(
    *,
    captured_id: str,
    username: str,
    display_name: str,
    spec: QuerySpec,
    evidence,
    captured_at: str,
    preset: str | None = None,
) -> dict:
    """Assemble the attributed query_log document from a spec + its live explain Evidence.
    Stores the query SPEC and ranking metrics only — never threaded into a v1 EvidencePack;
    the diagnose pack re-explains fresh."""
    query_filter, query_sort, limit = build_query(spec)
    metrics = evidence.metrics
    signal = slow_signal(metrics)
    return {
        "_id": captured_id,
        "namespace": NAMESPACE,
        "preset": preset,
        "user": {"username": username, "display_name": display_name},
        "query": {
            "filter": query_filter,
            "sort": [[field, direction] for field, direction in query_sort],
            "limit": limit,
        },
        "metrics": {
            "docs_examined": metrics.docs_examined,
            "docs_returned": metrics.docs_returned,
            "total_keys_examined": metrics.total_keys_examined,
            "millis": metrics.millis,
            "stages": list(metrics.stages),
            "has_blocking_sort": metrics.has_blocking_sort,
        },
        "signal": {
            "is_slow": signal.is_slow,
            "severity": signal.severity,
            "score": signal.score,
            "ratio": signal.ratio,
            "blocking_sort": signal.blocking_sort,
            "collscan": signal.collscan,
        },
        "captured_at": captured_at,
    }
