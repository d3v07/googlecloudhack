from enum import StrEnum


class Phase(StrEnum):
    DIAGNOSE = "diagnose"
    APPROVE = "approve"
    VERIFY = "verify"


class InvalidPhaseTransition(ValueError):
    pass


_NEXT_PHASE = {
    Phase.DIAGNOSE: Phase.APPROVE,
    Phase.APPROVE: Phase.VERIFY,
}


def assert_phase_transition(current: Phase, target: Phase) -> None:
    expected = _NEXT_PHASE.get(current)
    if expected is not target:
        raise InvalidPhaseTransition(
            f"invalid phase transition: {current.value} -> {target.value}; "
            f"expected {expected.value if expected else 'terminal'}"
        )


def next_phase(current: Phase) -> Phase:
    try:
        return _NEXT_PHASE[current]
    except KeyError as exc:
        raise InvalidPhaseTransition(f"{current.value} is terminal") from exc
