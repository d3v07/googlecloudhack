import json
import pathlib

from controller.diagnosis import diagnose
from controller.schemas import Severity

GOLDEN = pathlib.Path("seed/fixtures/fixture_results.golden.json")

# the ESR-correct order for the #9 fixture (derived from the query, NOT read from the
# golden's `indexes.*.keys` — those are order-corrupted by dict+sort_keys serialization)
EXPECTED_C = (("storeLocation", 1), ("saleDate", -1), ("customer.age", 1))
WRONG_B = (("storeLocation", 1), ("customer.age", 1), ("saleDate", -1))


def _golden() -> dict:
    return json.loads(GOLDEN.read_text())


def _query() -> tuple[dict, list[tuple[str, int]]]:
    g = _golden()
    query_filter = g["query"]["filter"]
    query_sort = [(field, direction) for field, direction in g["query"]["sort"].items()]
    return query_filter, query_sort


def test_recommends_esr_order_c_for_the_fixture_trap():
    query_filter, query_sort = _query()
    trap = _golden()["results"]["indexB"]  # B present -> blocking sort, the trap state

    diagnosis = diagnose(
        query_filter, query_sort,
        has_blocking_sort=trap["hasSort"],
        current_index=trap["indexName"],
    )

    assert diagnosis.recommendation.index_spec == EXPECTED_C
    assert diagnosis.finding.severity is Severity.HIGH


def test_recommendation_is_not_the_obvious_wrong_b_order():
    query_filter, query_sort = _query()

    diagnosis = diagnose(query_filter, query_sort, has_blocking_sort=True)

    assert diagnosis.recommendation.index_spec != WRONG_B


def test_finding_names_the_blocking_sort():
    query_filter, query_sort = _query()

    diagnosis = diagnose(query_filter, query_sort, has_blocking_sort=True, current_index="esr_wrong_B")

    assert "sort" in diagnosis.finding.problem.lower()
    assert diagnosis.finding.evidence_refs == ("esr_wrong_B",)


def test_esr_derivation_is_real_logic_not_a_fixture_lookup():
    # different field names entirely — proves the rule, not a hardcoded mapping
    query_filter = {"region": "west", "price": {"$gte": 10, "$lte": 99}}
    query_sort = [("ts", -1)]

    diagnosis = diagnose(query_filter, query_sort, has_blocking_sort=True)

    assert diagnosis.recommendation.index_spec == (("region", 1), ("ts", -1), ("price", 1))


def test_no_blocking_sort_yields_low_severity_and_same_esr_index():
    query_filter = {"region": "west", "price": {"$gt": 10}}
    query_sort = [("ts", 1)]

    diagnosis = diagnose(query_filter, query_sort, has_blocking_sort=False)

    assert diagnosis.finding.severity is Severity.LOW
    assert diagnosis.recommendation.index_spec == (("region", 1), ("ts", 1), ("price", 1))
