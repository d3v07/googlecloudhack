"""Deterministic ESR diagnosis: turn a slow query + its explain signal into a
Finding and the ESR-correct index Recommendation.

Scoped to the single-equality / single-or-multi-sort / single-or-multi-range query
shape (the #9 fixture). The recommendation orders index keys by the ESR rule —
Equality, then Sort, then Range — which is what lets the index serve the sort order
and eliminates a blocking in-memory SORT. Pure: no I/O, fully offline-testable.
"""

from collections.abc import Mapping, Sequence

from controller.schemas import Diagnosis, Finding, Recommendation, Severity

_RANGE_OPS = ("$gt", "$gte", "$lt", "$lte")


def _classify(
    query_filter: Mapping[str, object],
    query_sort: Sequence[tuple[str, int]],
) -> tuple[list[str], list[tuple[str, int]], list[str]]:
    equality: list[str] = []
    range_fields: list[str] = []
    for field, condition in query_filter.items():
        if isinstance(condition, Mapping) and any(op in condition for op in _RANGE_OPS):
            range_fields.append(field)
        else:
            equality.append(field)
    sort_fields = [(field, int(direction)) for field, direction in query_sort]
    return equality, sort_fields, range_fields


def _esr_index(
    equality: list[str],
    sort_fields: list[tuple[str, int]],
    range_fields: list[str],
) -> tuple[tuple[str, int], ...]:
    keys: list[tuple[str, int]] = [(field, 1) for field in equality]
    keys += sort_fields
    keys += [(field, 1) for field in range_fields]
    return tuple(keys)


def diagnose(
    query_filter: Mapping[str, object],
    query_sort: Sequence[tuple[str, int]],
    *,
    has_blocking_sort: bool,
    current_index: str | None = None,
) -> Diagnosis:
    equality, sort_fields, range_fields = _classify(query_filter, query_sort)
    recommended = _esr_index(equality, sort_fields, range_fields)
    sort_names = [field for field, _ in sort_fields]
    ordering = f"Equality{equality} -> Sort{sort_names} -> Range{range_fields}"

    if has_blocking_sort:
        finding = Finding(
            problem=(
                "Query performs a blocking in-memory SORT: the serving index orders a "
                "Range field ahead of the Sort field, so the index cannot supply the "
                "requested order and every matched document is sorted in memory."
            ),
            severity=Severity.HIGH,
            evidence_refs=(current_index or "explain",),
        )
        rationale = (
            f"Reorder the index by the ESR rule ({ordering}). With Sort placed before "
            "Range, the index yields documents already in sort order, removing the "
            "blocking SORT stage and the over-scan it causes."
        )
    else:
        finding = Finding(
            problem="No blocking sort detected; query is served in index order.",
            severity=Severity.LOW,
            evidence_refs=(current_index or "explain",),
        )
        rationale = f"Index already follows the ESR rule ({ordering}); no change needed."

    return Diagnosis(
        finding=finding,
        recommendation=Recommendation(index_spec=recommended, rationale=rationale),
    )
