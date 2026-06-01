"""Scripted DIAGNOSE → APPROVE → VERIFY remediation flow.

Runs the full phase cycle: capture before-evidence, diagnose the ESR problem,
auto-approve, apply a scratch index, capture after-evidence, then clean up.
"""

from datetime import datetime, timezone

from controller.backends import Backend
from controller.diagnosis import diagnose
from controller.pack import build_pack, pack_evidence_hash
from controller.phases import Phase, assert_phase_transition
from controller.schemas import (
    Decision,
    DecisionAction,
    EvidencePack,
    PackStatus,
    PhaseTransition,
)

# fixture constants — match seed/seed_demo_fixture.py
INDEX_B_NAME = "esr_wrong_B"
INDEX_C_NAME = "esr_right_C"


async def run_remediation(
    backend: Backend,
    run_id: str,
    namespace: str,
    query_filter: dict,
    query_sort: list[tuple[str, int]],
    limit: int,
    created_at: str | None = None,
) -> EvidencePack:
    if created_at is None:
        created_at = datetime.now(timezone.utc).isoformat()

    phase = Phase.DIAGNOSE
    before = await backend.explain(query_filter, query_sort, limit, hint=INDEX_B_NAME)

    diagnosis = diagnose(
        query_filter,
        query_sort,
        has_blocking_sort=before.metrics.has_blocking_sort,
        current_index=INDEX_B_NAME,
    )
    rec = diagnosis.recommendation
    finding = diagnosis.finding

    phase_log: list[PhaseTransition] = [
        PhaseTransition(from_phase=None, to_phase=Phase.DIAGNOSE)
    ]

    # auto-approve
    assert_phase_transition(phase, Phase.APPROVE)
    phase = Phase.APPROVE
    phase_log.append(PhaseTransition(from_phase=Phase.DIAGNOSE, to_phase=Phase.APPROVE))
    evidence_hash = pack_evidence_hash(before, rec)
    decision = Decision(
        action=DecisionAction.APPROVE,
        evidence_hash=evidence_hash,
        phase=Phase.APPROVE,
    )

    assert_phase_transition(phase, Phase.VERIFY)
    phase = Phase.VERIFY
    phase_log.append(PhaseTransition(from_phase=Phase.APPROVE, to_phase=Phase.VERIFY))

    scratch_name = f"{INDEX_C_NAME}__scratch"
    scratch_keys = list(rec.index_spec)

    await backend.apply_index(scratch_keys, scratch_name)
    try:
        # hint by key pattern — works even if an index with equivalent keys already exists
        after = await backend.explain(query_filter, query_sort, limit, hint=scratch_keys)
    finally:
        await backend.drop_index(scratch_name)

    status = PackStatus.VERIFIED if not after.metrics.has_blocking_sort else PackStatus.DIAGNOSED

    return build_pack(
        run_id=run_id,
        namespace=namespace,
        created_at=created_at,
        before=before,
        finding=finding,
        recommendation=rec,
        status=status,
        after=after,
        decision=decision,
        phase_log=phase_log,
    )
