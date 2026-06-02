"""CI-safe tests for the eval grader (#38).

The deterministic graders are pure, so they run everywhere. The live agent run
is exercised only when RUN_API_TOKEN + API_URL are set (skipped in CI).
"""

import os

import pytest

from evals.grade import (
    ESR_CORRECT_C,
    OBVIOUS_WRONG_B,
    EXPECTED_LEDGER_COLLECTIONS,
    EXPECTED_TARGET_INDEXES,
    Scorecard,
    grade_agent_engine_used,
    grade_approval_verified,
    grade_esr_correct,
    grade_ledger_records,
    grade_latency,
    grade_narrative_grounded,
    grade_no_extra_indexes,
    grade_no_mutation_before_approval,
    grade_phase_gate,
)


def test_esr_correct_passes_on_index_c():
    assert grade_esr_correct(ESR_CORRECT_C).passed


def test_esr_correct_fails_on_obvious_index_b():
    check = grade_esr_correct(OBVIOUS_WRONG_B)
    assert not check.passed
    assert "B" in check.detail


def test_esr_correct_accepts_list_of_lists():
    # the API returns index_spec as JSON lists, not tuples
    spec = [["storeLocation", 1], ["saleDate", -1], ["customer.age", 1]]
    assert grade_esr_correct(spec).passed


def test_esr_correct_fails_on_unexpected_index():
    check = grade_esr_correct([["storeLocation", 1]])
    assert not check.passed
    assert "unexpected" in check.detail


def test_scorecard_summary_and_passed_state():
    card = Scorecard()
    card.add("one", True, "ok")
    card.add("two", False, "bad")

    assert not card.passed
    assert card.summary == "1/2 checks passed"


def test_phase_gate_blocks_writes_outside_verify():
    assert grade_phase_gate().passed


def test_narrative_grounded_passes_on_real_numbers():
    narrative = (
        "The serving index forces a blocking in-memory SORT, scanning 17,209 keys; "
        "the ESR fix drops that to 64 keys with no sort."
    )
    assert grade_narrative_grounded(narrative).passed


def test_narrative_grounded_catches_fabricated_numbers():
    narrative = "This blocking sort scanned 999999 documents and cost 42424 reads."
    check = grade_narrative_grounded(narrative)
    assert not check.passed
    assert "fabricated" in check.detail


def test_narrative_grounded_requires_sort_mention():
    check = grade_narrative_grounded("Recommend a better index for performance.")
    assert not check.passed


def test_narrative_grounded_tolerates_missing_narrative():
    # /run packs are deterministic-only (no narrative) — not a grounding failure
    assert grade_narrative_grounded(None).passed


def test_latency_recorded():
    assert grade_latency(1.5).passed
    assert not grade_latency(None).passed


def test_agent_engine_path_requires_phase_log_note():
    assert grade_agent_engine_used({"phase_log": [{"note": "agent_engine=resource"}]}).passed
    assert not grade_agent_engine_used({"phase_log": [{"note": ""}]}).passed


def test_no_mutation_before_approval_compares_indexes():
    indexes = {"_id_", "esr_wrong_B", "esr_right_C"}
    assert grade_no_mutation_before_approval(indexes, set(indexes)).passed
    assert not grade_no_mutation_before_approval(indexes, indexes | {"extra"}).passed


def test_ledger_records_require_all_diagram_collections():
    assert grade_ledger_records(set(EXPECTED_LEDGER_COLLECTIONS)).passed
    assert not grade_ledger_records({"evidence_packs"}).passed


def test_approval_verified_requires_hash_preservation_and_key_drop():
    diagnosed = {
        "status": "diagnosed",
        "evidence_hash": "a" * 64,
        "before": {"metrics": {"total_keys_examined": 17209}},
    }
    verified = {
        "status": "verified",
        "evidence_hash": "a" * 64,
        "after": {"metrics": {"total_keys_examined": 64, "has_blocking_sort": False}},
    }
    assert grade_approval_verified(diagnosed, verified).passed

    drifted = {**verified, "evidence_hash": "b" * 64}
    assert not grade_approval_verified(diagnosed, drifted).passed


def test_no_extra_indexes_allows_only_seeded_fixture_indexes():
    assert grade_no_extra_indexes(set(EXPECTED_TARGET_INDEXES)).passed
    assert not grade_no_extra_indexes(EXPECTED_TARGET_INDEXES | {"gcrah_rec_extra"}).passed


@pytest.mark.skipif(
    not (os.environ.get("RUN_API_TOKEN") and os.environ.get("API_URL")),
    reason="live agent run needs RUN_API_TOKEN + API_URL",
)
def test_live_agent_run_scores_well():
    from evals.grade import Scorecard
    from evals.run_eval import grade_live

    card = Scorecard()
    pack = grade_live(card, os.environ["API_URL"], os.environ["RUN_API_TOKEN"])
    assert pack is not None
    assert card.passed, card.summary
