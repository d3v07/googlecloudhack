"""Reset the demo collection to the WORKLOAD baseline index set and (optionally) verify that the
guided presets exhibit the intended explain behaviour against the live cluster.

Baseline = {storeLocation:1} + {purchaseMethod:1} only. The ESR-correct compound indexes are
deliberately absent, so a trap query (equality + saleDate sort) is forced into a blocking
in-memory SORT and the DBRE's later fix verifies as a real improvement. Run this BETWEEN demos to
restore the trap — an approved fix removes it for a whole store/method class.

Usage:
  export MDB_MCP_CONNECTION_STRING=...
  uv run python seed/seed_workload.py            # reset baseline indexes
  uv run python seed/seed_workload.py verify     # reset + explain every preset + assert contract
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pymongo import MongoClient  # noqa: E402

from api.secrets import get_mongo_connection_string  # noqa: E402
from controller.explain import capture_evidence  # noqa: E402
from controller.workload import (  # noqa: E402
    APPLIED_INDEX_PREFIX,
    BASELINE_INDEXES,
    DEFAULT_MAX_TIME_MS,
    LEGACY_INDEX_NAMES,
    NAMESPACE_COLL,
    NAMESPACE_DB,
    PRESETS,
    SLOW_RATIO,
    build_query,
    slow_signal,
)


def reset_baseline(coll) -> None:
    count = coll.estimated_document_count()
    print(f"collection {NAMESPACE_DB}.{NAMESPACE_COLL}: ~{count} docs")
    if count == 0:
        sys.exit("collection is empty — run seed/seed_demo_fixture.py seed first")
    existing = [ix["name"] for ix in coll.list_indexes()]
    to_drop = [
        name
        for name in existing
        if name in LEGACY_INDEX_NAMES or name.startswith(APPLIED_INDEX_PREFIX)
    ]
    for name in to_drop:
        coll.drop_index(name)
        print(f"  dropped {name}")
    for keys, name in BASELINE_INDEXES:
        coll.create_index(keys, name=name)
        print(f"  ensured {name} {keys}")
    print(f"baseline indexes now: {[ix['name'] for ix in coll.list_indexes()]}")


def verify_presets(coll) -> bool:
    print("\n--- preset explain contract ---")
    print(f"{'preset':16} {'intent':8} {'scan':9} {'sort':6} {'ratio':>10} {'slow':6} verdict")
    ok = True
    for preset in PRESETS:
        query_filter, query_sort, limit = build_query(preset.spec)
        evidence = capture_evidence(
            coll, query_filter, query_sort, limit, max_time_ms=DEFAULT_MAX_TIME_MS
        )
        signal = slow_signal(evidence.metrics)
        stages = evidence.metrics.stages
        scan = "COLLSCAN" if signal.collscan else ("IXSCAN" if "IXSCAN" in stages else "?")
        if preset.intent == "trap":
            passed = signal.is_slow and (signal.blocking_sort or signal.collscan)
        else:
            passed = (not signal.blocking_sort) and signal.ratio < SLOW_RATIO
        ok = ok and passed
        print(
            f"{preset.key:16} {preset.intent:8} {scan:9} {str(signal.blocking_sort):6} "
            f"{signal.ratio:>10.1f} {str(signal.is_slow):6} {'PASS' if passed else 'FAIL'}"
        )
    print("contract:", "ALL PASS" if ok else "FAILED")
    return ok


def main() -> int:
    step = sys.argv[1] if len(sys.argv) > 1 else "reset"
    if step not in ("reset", "verify"):
        sys.exit("usage: seed_workload.py [reset|verify]")
    client = MongoClient(get_mongo_connection_string())
    try:
        coll = client[NAMESPACE_DB][NAMESPACE_COLL]
        reset_baseline(coll)
        if step == "verify" and not verify_presets(coll):
            return 1
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
