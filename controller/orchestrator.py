"""DIAGNOSE → (human APPROVE) → VERIFY remediation flow, split so the database mutation
happens ONLY after an explicit human approval.

- run_diagnosis: read-only. Capture before-evidence (hinting the wrong index so the ESR
  trap is visible), derive the ESR recommendation, emit a DIAGNOSED pack — no decision,
  no mutation.
- apply_and_verify: the post-approval half. Apply the recommended index (the approved
  mutation) and measure the after-evidence.
- reject_pack: record a human rejection — no mutation, no after-evidence.
"""

import asyncio
from datetime import datetime, timezone

from controller.backends import Backend
from controller.diagnosis import diagnose
from controller.narrate import Narrator
from controller.pack import build_pack
from controller.phases import Phase, assert_phase_transition
from controller.schemas import (
    Decision,
    DecisionAction,
    EvidencePack,
    PackStatus,
    PhaseTransition,
    Recommendation,
)

# fixture constants — match seed/seed_demo_fixture.py
INDEX_B_NAME = "esr_wrong_B"
INDEX_C_NAME = "esr_right_C"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _maybe_narrate(pack: EvidencePack, narrator: Narrator | None) -> EvidencePack:
    if narrator is None:
        return pack
    # narrate may do network I/O (Gemini) — keep it off the event loop
    narrative = await asyncio.to_thread(narrator.narrate, pack)
    return pack.model_copy(update={"narrative": narrative})


def _recommended_index_name(recommendation: Recommendation) -> str:
    parts = "_".join(f"{field}{direction}" for field, direction in recommendation.index_spec)
    return f"gcrah_rec_{parts}"[:120]


async def run_diagnosis(
    backend: Backend,
    run_id: str,
    namespace: str,
    query_filter: dict,
    query_sort: list[tuple[str, int]],
    limit: int,
    created_at: str | None = None,
    narrator: Narrator | None = None,
    current_index: str = INDEX_B_NAME,
) -> EvidencePack:
    """Read-only DIAGNOSE phase. Returns a DIAGNOSED pack with NO decision and NO mutation —
    the human approves (via the API) before anything is applied. The before-explain hints the
    wrong index so the ESR blocking-sort trap is visible in the evidence."""
    created_at = created_at or _now()
    before = await backend.explain(query_filter, query_sort, limit, hint=current_index)
    diagnosis = diagnose(
        query_filter,
        query_sort,
        has_blocking_sort=before.metrics.has_blocking_sort,
        current_index=current_index,
    )
    pack = build_pack(
        run_id=run_id,
        namespace=namespace,
        created_at=created_at,
        before=before,
        finding=diagnosis.finding,
        recommendation=diagnosis.recommendation,
        status=PackStatus.DIAGNOSED,
        phase_log=[PhaseTransition(from_phase=None, to_phase=Phase.DIAGNOSE)],
    )
    return await _maybe_narrate(pack, narrator)


async def apply_and_verify(
    backend: Backend,
    pack: EvidencePack,
    query_filter: dict,
    query_sort: list[tuple[str, int]],
    limit: int,
    narrator: Narrator | None = None,
) -> EvidencePack:
    """Post-approval APPLY + VERIFY. Applies the recommended index (the human-approved
    mutation) and captures after-evidence. VERIFIED if the blocking sort is gone, else
    APPROVED (applied, didn't help). evidence_hash is unchanged: it bound (before,
    recommendation) at diagnosis and neither changed, so the approved hash still holds."""
    if pack.status is not PackStatus.DIAGNOSED:
        raise ValueError(f"can only apply+verify a DIAGNOSED pack, got '{pack.status}'")

    phase_log = list(pack.phase_log)
    assert_phase_transition(Phase.DIAGNOSE, Phase.APPROVE)
    phase_log.append(PhaseTransition(from_phase=Phase.DIAGNOSE, to_phase=Phase.APPROVE))
    decision = Decision(
        action=DecisionAction.APPROVE, evidence_hash=pack.evidence_hash, phase=Phase.APPROVE
    )

    assert_phase_transition(Phase.APPROVE, Phase.VERIFY)
    phase_log.append(PhaseTransition(from_phase=Phase.APPROVE, to_phase=Phase.VERIFY))

    index_keys = list(pack.recommendation.index_spec)
    await backend.apply_index(index_keys, _recommended_index_name(pack.recommendation))
    # hint by key pattern so verify uses the recommended index even if it already existed
    # under another name (the apply was a conflict-absorbed no-op)
    after = await backend.explain(query_filter, query_sort, limit, hint=index_keys)

    status = PackStatus.VERIFIED if not after.metrics.has_blocking_sort else PackStatus.APPROVED
    updated = build_pack(
        run_id=pack.run_id,
        namespace=pack.namespace,
        created_at=pack.created_at,
        before=pack.before,
        finding=pack.finding,
        recommendation=pack.recommendation,
        status=status,
        after=after,
        decision=decision,
        phase_log=phase_log,
        narrative=pack.narrative,
    )
    return await _maybe_narrate(updated, narrator)


def reject_pack(pack: EvidencePack) -> EvidencePack:
    """Record a human rejection — no mutation, no after-evidence."""
    if pack.status is not PackStatus.DIAGNOSED:
        raise ValueError(f"can only reject a DIAGNOSED pack, got '{pack.status}'")
    assert_phase_transition(Phase.DIAGNOSE, Phase.APPROVE)
    decision = Decision(
        action=DecisionAction.REJECT, evidence_hash=pack.evidence_hash, phase=Phase.APPROVE
    )
    return build_pack(
        run_id=pack.run_id,
        namespace=pack.namespace,
        created_at=pack.created_at,
        before=pack.before,
        finding=pack.finding,
        recommendation=pack.recommendation,
        status=PackStatus.REJECTED,
        decision=decision,
        phase_log=[
            *pack.phase_log,
            PhaseTransition(from_phase=Phase.DIAGNOSE, to_phase=Phase.APPROVE),
        ],
        narrative=pack.narrative,
    )
