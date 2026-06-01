"""Fixture-contract test for the #9 primary fixture (B-vs-C ESR trap).

Validates the committed golden file (`seed/fixtures/fixture_results.golden.json`)
satisfies the ESR contract. Runs fully offline — no DB connection required — so it
is safe in CI. Regenerate the fixture against `target` with
`uv run python seed/seed_demo_fixture.py --all`.
"""

import hashlib
import json
import pathlib

GOLDEN = pathlib.Path("seed/fixtures/fixture_results.golden.json")


def _load() -> dict:
    return json.loads(GOLDEN.read_text())


def test_golden_exists_and_parses() -> None:
    assert GOLDEN.exists(), "golden file missing — run the seed script to generate it"
    data = _load()
    for key in ("query", "indexes", "results", "fixtureHash", "seed", "docCount"):
        assert key in data, f"golden missing top-level key: {key}"


def test_index_b_is_the_wrong_esr_order() -> None:
    """B places the Range key before the Sort key -> blocking sort."""
    b = _load()["results"]["indexB"]
    assert b["scan"] == "IXSCAN"
    assert b["hasSort"] is True, "B must require a blocking in-memory SORT"


def test_index_c_is_the_correct_esr_order() -> None:
    """C places Sort immediately after Equality -> index provides order, no sort."""
    c = _load()["results"]["indexC"]
    assert c["scan"] == "IXSCAN"
    assert c["hasSort"] is False, "C must NOT have a sort stage"
    assert c["indexName"] == "esr_right_C"


def test_c_examines_far_fewer_keys_than_b() -> None:
    """The real cost driver is index keys examined, not docs examined."""
    results = _load()["results"]
    b_keys = results["indexB"]["totalKeysExamined"]
    c_keys = results["indexC"]["totalKeysExamined"]
    assert c_keys < b_keys, "C should examine fewer index keys than B"
    # the trap is only convincing if the gap is large
    assert b_keys >= 10 * max(c_keys, 1), "B-vs-C keys-examined gap should be >= 10x"


def test_all_plans_return_the_same_rows() -> None:
    results = _load()["results"]
    counts = {name: r["nReturned"] for name, r in results.items()}
    assert len(set(counts.values())) == 1, f"plans returned different row counts: {counts}"


def test_fixture_hash_matches_recomputed() -> None:
    """The stored hash must match a recompute over everything except itself."""
    data = _load()
    stored = data.pop("fixtureHash")
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    recomputed = hashlib.sha256(canonical.encode()).hexdigest()
    assert recomputed == stored, "fixtureHash does not match canonical recompute"
