import pytest

from controller.phases import InvalidPhaseTransition, Phase, assert_phase_transition, next_phase


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (Phase.DIAGNOSE, Phase.APPROVE),
        (Phase.APPROVE, Phase.VERIFY),
    ],
)
def test_legal_phase_transitions(current, target):
    assert_phase_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (Phase.DIAGNOSE, Phase.DIAGNOSE),
        (Phase.DIAGNOSE, Phase.VERIFY),
        (Phase.APPROVE, Phase.DIAGNOSE),
        (Phase.APPROVE, Phase.APPROVE),
        (Phase.VERIFY, Phase.DIAGNOSE),
        (Phase.VERIFY, Phase.APPROVE),
        (Phase.VERIFY, Phase.VERIFY),
    ],
)
def test_illegal_phase_transitions_raise(current, target):
    with pytest.raises(InvalidPhaseTransition, match="invalid phase transition"):
        assert_phase_transition(current, target)


def test_next_phase_returns_expected_phase():
    assert next_phase(Phase.DIAGNOSE) is Phase.APPROVE
    assert next_phase(Phase.APPROVE) is Phase.VERIFY


def test_next_phase_rejects_terminal_phase():
    with pytest.raises(InvalidPhaseTransition, match="terminal"):
        next_phase(Phase.VERIFY)
