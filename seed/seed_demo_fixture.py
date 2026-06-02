"""Day-1 primary fixture (#9): the B-vs-C ESR index trap on `target`.

Seeds a cloned, bloated `sample_supplies.sales_agent_demo` collection where the
*obvious* index (B) loses to the *correct* ESR-ordered index (C) for one query.

The query has all three ESR ingredients:
    Equality : storeLocation == "Denver"
    Sort     : saleDate descending
    Range    : customer.age between AGE_LO and AGE_HI
with a small `.limit()` that amplifies the difference.

    Index B (obvious, WRONG — Range before Sort):
        {storeLocation: 1, "customer.age": 1, saleDate: -1}
        -> cannot use index order for the sort -> blocking in-memory SORT of every
           matching doc, then limit. Huge totalDocsExamined.

    Index C (correct ESR — Equality, Sort, Range):
        {storeLocation: 1, saleDate: -1, "customer.age": 1}
        -> index already yields saleDate order -> NO sort stage; streams in order
           and stops at the limit. Tiny totalDocsExamined.

Determinism: all generated values come from a fixed-seed RNG, so re-running on a
fresh `target` reproduces the same data and the same structural explain results.
The golden file + hash cover *structural* facts and deterministic counters only —
never wall-clock timings (executionTimeMillis), which are environment-dependent.

Usage (one command does everything: seed -> build indexes -> explain -> golden):
    uv run python seed/seed_demo_fixture.py --all

Sub-steps:
    uv run python seed/seed_demo_fixture.py seed     # clone + bloat to --count docs
    uv run python seed/seed_demo_fixture.py indexes  # (re)create indexes B and C
    uv run python seed/seed_demo_fixture.py verify    # run the explain comparison
    uv run python seed/seed_demo_fixture.py golden    # write fixture_results.golden.json

Connection string is read from the environment (never hard-coded):
    MONGODB_TARGET_URI   preferred
    or built from MONGODB_VERIFY_USER / MONGODB_VERIFY_PW (dev fallback)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pymongo import ASCENDING, DESCENDING, MongoClient

# ---- fixture constants (the contract lives here) ---------------------------

DEMO_DB = "sample_supplies"
DEMO_COLL = "sales_agent_demo"

SEED = 42
DEFAULT_COUNT = 300_000
BATCH = 5_000

STORES = ["Austin", "Denver", "London", "New York", "San Diego", "Seattle"]
PURCHASE_METHODS = ["In store", "Online", "Phone"]
AGE_LO, AGE_HI = 16, 75
DATE_START = datetime(2013, 1, 1, tzinfo=timezone.utc)
DATE_END = datetime(2017, 12, 31, tzinfo=timezone.utc)

# the query under test
Q_STORE = "Denver"
Q_AGE_LO, Q_AGE_HI = 30, 50
Q_LIMIT = 20

QUERY_FILTER = {"storeLocation": Q_STORE, "customer.age": {"$gte": Q_AGE_LO, "$lte": Q_AGE_HI}}
QUERY_SORT = [("saleDate", DESCENDING)]

INDEX_B_NAME = "esr_wrong_B"
INDEX_B_KEYS = [("storeLocation", ASCENDING), ("customer.age", ASCENDING), ("saleDate", DESCENDING)]
INDEX_C_NAME = "esr_right_C"
INDEX_C_KEYS = [("storeLocation", ASCENDING), ("saleDate", DESCENDING), ("customer.age", ASCENDING)]

GOLDEN_PATH = Path(__file__).parent / "fixtures" / "fixture_results.golden.json"


# ---- connection -----------------------------------------------------------


def get_uri() -> str:
    uri = os.environ.get("MONGODB_TARGET_URI")
    if uri:
        return uri
    uri = os.environ.get("MDB_MCP_CONNECTION_STRING")
    if uri:
        return uri
    user = os.environ.get("MONGODB_VERIFY_USER")
    pw = os.environ.get("MONGODB_VERIFY_PW")
    if user and pw:
        return f"mongodb+srv://{user}:{pw}@target.7ehydqs.mongodb.net/?retryWrites=true&w=majority"
    sys.exit(
        "No connection string. Set MONGODB_TARGET_URI (preferred), "
        "MDB_MCP_CONNECTION_STRING, or "
        "MONGODB_VERIFY_USER / MONGODB_VERIFY_PW in the environment."
    )


# ---- seeding --------------------------------------------------------------


def seed(client: MongoClient, count: int) -> None:
    """Generate slim demo docs deterministically.

    We deliberately do NOT clone the full source docs: the real `sales` doc carries
    a large `items` array (~865 bytes/doc) that the ESR trap never touches, and the
    M0 free tier has only 512MB. The trap is a property of index *structure* vs the
    query's equality/sort/range fields, so we keep only those three fields plus a
    couple of cheap extras. Slim docs (~100 bytes) let 300k fit with room to spare,
    and the explain plans are identical to what the full docs would produce.
    """
    demo = client[DEMO_DB][DEMO_COLL]
    demo.drop()
    print(f"dropped {DEMO_DB}.{DEMO_COLL} (clean slate)")

    rng = random.Random(SEED)
    span = int((DATE_END - DATE_START).total_seconds())

    buf: list[dict] = []
    written = 0
    for i in range(count):
        doc = {
            "storeLocation": STORES[i % len(STORES)],  # even spread across stores
            "saleDate": DATE_START + timedelta(seconds=rng.randint(0, span)),
            "customer": {"age": rng.randint(AGE_LO, AGE_HI)},
            "purchaseMethod": PURCHASE_METHODS[rng.randrange(len(PURCHASE_METHODS))],
        }
        buf.append(doc)
        if len(buf) >= BATCH:
            demo.insert_many(buf, ordered=False)
            written += len(buf)
            buf.clear()
            print(f"  inserted {written}/{count}", end="\r", flush=True)
    if buf:
        demo.insert_many(buf, ordered=False)
        written += len(buf)
    print(f"\nseeded {written} slim docs into {DEMO_DB}.{DEMO_COLL}")


def build_indexes(client: MongoClient) -> None:
    demo = client[DEMO_DB][DEMO_COLL]
    # drop any prior fixture indexes so this is idempotent
    for name in (INDEX_B_NAME, INDEX_C_NAME):
        try:
            demo.drop_index(name)
        except Exception:
            pass
    demo.create_index(INDEX_B_KEYS, name=INDEX_B_NAME)
    demo.create_index(INDEX_C_KEYS, name=INDEX_C_NAME)
    print(f"created indexes: {INDEX_B_NAME} (wrong), {INDEX_C_NAME} (correct ESR)")


# ---- explain extraction ---------------------------------------------------


def _walk_stages(plan: dict) -> list[str]:
    """Flatten queryPlanner.winningPlan into an ordered list of stage names."""
    stages: list[str] = []
    node = plan
    while isinstance(node, dict):
        stage = node.get("stage")
        if stage:
            stages.append(stage)
        if "inputStage" in node:
            node = node["inputStage"]
        elif "inputStages" in node:  # rare for these plans; record + stop
            for child in node["inputStages"]:
                stages.extend(_walk_stages(child))
            break
        else:
            break
    return stages


def run_explain(client: MongoClient, hint) -> dict:
    """Execute the query under an explicit index hint and extract structural facts."""
    demo = client[DEMO_DB][DEMO_COLL]
    cursor = demo.find(QUERY_FILTER, sort=QUERY_SORT, limit=Q_LIMIT)
    if hint is not None:
        cursor = cursor.hint(hint)
    ex = cursor.explain()

    winning = ex["queryPlanner"]["winningPlan"]
    stages = _walk_stages(winning)
    stats = ex["executionStats"]
    return {
        "stages": stages,
        "hasSort": "SORT" in stages,
        "hasFetch": "FETCH" in stages,
        "scan": "IXSCAN" if "IXSCAN" in stages else ("COLLSCAN" if "COLLSCAN" in stages else "?"),
        "indexName": _index_name(winning),
        "nReturned": stats["nReturned"],
        "totalKeysExamined": stats["totalKeysExamined"],
        "totalDocsExamined": stats["totalDocsExamined"],
    }


def _index_name(plan: dict) -> str | None:
    node = plan
    while isinstance(node, dict):
        if node.get("stage") == "IXSCAN":
            return node.get("indexName")
        node = node.get("inputStage")
    return None


def verify(client: MongoClient) -> dict:
    """Run COLLSCAN / B / C and assert the ESR contract holds."""
    results = {
        "collscan": run_explain(client, [("$natural", ASCENDING)]),
        "indexB": run_explain(client, INDEX_B_NAME),
        "indexC": run_explain(client, INDEX_C_NAME),
    }

    b, c = results["indexB"], results["indexC"]
    # The cost driver here is *keys examined*, not docs examined: with a small
    # .limit(), the FETCH runs after SORT+limit, so both plans FETCH only ~20 docs.
    # The difference is that B must scan + blocking-sort every matching index key,
    # while C walks the index already in sort order and stops early.
    checks = {
        "B uses a blocking in-memory SORT": b["hasSort"] is True,
        "C has NO sort stage": c["hasSort"] is False,
        "C examines far fewer index keys than B": c["totalKeysExamined"] < b["totalKeysExamined"],
        "the keys-examined gap is large (>=10x)": b["totalKeysExamined"]
        >= 10 * max(c["totalKeysExamined"], 1),
        "both return the same rows": b["nReturned"] == c["nReturned"] == Q_LIMIT,
        "C uses the correct ESR index": c["indexName"] == INDEX_C_NAME,
    }

    print("\n--- explain comparison ---")
    for label, r in results.items():
        print(
            f"  {label:9} scan={r['scan']:8} sort={str(r['hasSort']):5} "
            f"keysExamined={r['totalKeysExamined']:>7} docsExamined={r['totalDocsExamined']:>7} "
            f"nReturned={r['nReturned']}"
        )
    print("--- contract ---")
    ok = True
    for label, passed in checks.items():
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
        ok = ok and passed
    if not ok:
        sys.exit("CONTRACT FAILED — fixture does not exhibit the B-vs-C trap.")
    print("contract: ALL PASS")
    results["_contract"] = checks
    return results


# ---- golden ---------------------------------------------------------------


def write_golden(results: dict, count: int) -> None:
    payload = {
        "fixtureVersion": 1,
        "seed": SEED,
        "docCount": count,
        "namespace": f"{DEMO_DB}.{DEMO_COLL}",
        "query": {
            "filter": {
                "storeLocation": Q_STORE,
                "customer.age": {"$gte": Q_AGE_LO, "$lte": Q_AGE_HI},
            },
            "sort": {"saleDate": -1},
            "limit": Q_LIMIT,
        },
        "indexes": {
            "B_wrong": {"keys": _keys_to_pairs(INDEX_B_KEYS), "name": INDEX_B_NAME},
            "C_right": {"keys": _keys_to_pairs(INDEX_C_KEYS), "name": INDEX_C_NAME},
        },
        "results": {k: v for k, v in results.items() if not k.startswith("_")},
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload["fixtureHash"] = hashlib.sha256(canonical.encode()).hexdigest()

    GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"wrote golden -> {GOLDEN_PATH}  (fixtureHash={payload['fixtureHash'][:12]}…)")


def _keys_to_pairs(keys) -> list:
    # ordered [field, direction] pairs — a dict would lose key order under sort_keys,
    # and field order IS the ESR distinction between index B and C.
    return [[field, direction] for field, direction in keys]


# ---- cli ------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description="Seed + verify the B-vs-C ESR fixture on target.")
    ap.add_argument(
        "step",
        nargs="?",
        default="all",
        choices=["all", "seed", "indexes", "verify", "golden"],
        help="which step to run (default: all)",
    )
    ap.add_argument("--count", type=int, default=DEFAULT_COUNT, help="docs to seed")
    ap.add_argument("--all", dest="all_flag", action="store_true", help="alias for step=all")
    args = ap.parse_args()
    step = "all" if args.all_flag else args.step

    client = MongoClient(get_uri())
    try:
        if step in ("all", "seed"):
            seed(client, args.count)
        if step in ("all", "indexes"):
            build_indexes(client)
        results = None
        if step in ("all", "verify", "golden"):
            results = verify(client)
        if step in ("all", "golden"):
            write_golden(results, args.count)
    finally:
        client.close()


if __name__ == "__main__":
    main()
