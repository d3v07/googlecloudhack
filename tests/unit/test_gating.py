from agents.gating import is_allowed, make_gate
from controller.phases import Phase


class _Tool:
    def __init__(self, name):
        self.name = name


def test_write_tool_blocked_outside_verify():
    blocked = make_gate(Phase.DIAGNOSE)(_Tool("create-index"), {}, None)

    assert blocked["blocked"] is True
    assert blocked["phase"] == "diagnose"
    assert "create-index" in blocked["reason"]


def test_write_tool_blocked_during_approval():
    assert make_gate(Phase.APPROVE)(_Tool("create-index"), {}, None)["blocked"] is True


def test_write_tool_allowed_in_verify():
    assert make_gate(Phase.VERIFY)(_Tool("create-index"), {}, None) is None


def test_read_tools_allowed_in_every_phase():
    for phase in (Phase.DIAGNOSE, Phase.APPROVE, Phase.VERIFY):
        assert make_gate(phase)(_Tool("explain"), {}, None) is None
        assert make_gate(phase)(_Tool("explain_slow_query"), {}, None) is None
        assert make_gate(phase)(_Tool("compare_candidate_indexes"), {}, None) is None
        assert make_gate(phase)(_Tool("diagnose_candidate"), {}, None) is None
        assert make_gate(phase)(_Tool("rationalize_recommendation"), {}, None) is None
        assert make_gate(phase)(_Tool("diagnose_index"), {}, None) is None


def test_is_allowed_matrix():
    assert is_allowed(Phase.VERIFY, "create-index")
    assert not is_allowed(Phase.DIAGNOSE, "create-index")
    assert not is_allowed(Phase.APPROVE, "drop-index")
    assert is_allowed(Phase.DIAGNOSE, "diagnose_index")
    assert is_allowed(Phase.DIAGNOSE, "compare_candidate_indexes")
