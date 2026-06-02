"""Assemble an EvidencePack and compute its approval-binding hash.

The hash binds (before-evidence + recommendation): the human approves "apply THIS
index given THIS evidence", so the token must pin both — not the evidence alone.
"""

from collections.abc import Sequence

from controller.ledger import evidence_hash
from controller.schemas import (
    Decision,
    Evidence,
    EvidencePack,
    Finding,
    AgentTraceEvent,
    PackStatus,
    PhaseTransition,
    Recommendation,
)


def pack_evidence_hash(before: Evidence, recommendation: Recommendation) -> str:
    return evidence_hash({"evidence": before, "recommendation": recommendation})


def build_pack(
    *,
    run_id: str,
    namespace: str,
    created_at: str,
    before: Evidence,
    finding: Finding,
    recommendation: Recommendation,
    status: PackStatus = PackStatus.DIAGNOSED,
    after: Evidence | None = None,
    decision: Decision | None = None,
    phase_log: Sequence[PhaseTransition] = (),
    agent_trace: Sequence[AgentTraceEvent] = (),
    narrative: str | None = None,
) -> EvidencePack:
    return EvidencePack(
        run_id=run_id,
        namespace=namespace,
        created_at=created_at,
        status=status,
        before=before,
        after=after,
        finding=finding,
        recommendation=recommendation,
        decision=decision,
        phase_log=tuple(phase_log),
        agent_trace=tuple(agent_trace),
        evidence_hash=pack_evidence_hash(before, recommendation),
        narrative=narrative,
    )
