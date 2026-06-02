"""Day-3 live demo (#40): drive the deterministic orchestrator over the live fixture so
the agent visibly CATCHES the ESR trap.

The orchestrator's before-explain hints the obvious index B, so the captured plan is the
blocking-sort one (severity HIGH) — not the already-optimal plan the unhinted optimizer
would pick on the two-index fixture. It then recommends + applies C, verifies the fix,
and (with a narrator) explains it with Gemini. Emits a persisted EvidencePack the
dashboard can render.

Run: uv run --with python-dotenv python agents/demo.py
"""

import asyncio
import os
from pathlib import Path

from controller.backends import PymongoBackend
from controller.demo_fixture import COLL, DB, LIMIT, QUERY_FILTER, QUERY_SORT
from controller.narrate import Narrator
from controller.orchestrator import run_remediation
from controller.persistence import save_pack, write_pack
from controller.schemas import EvidencePack

# the deployed read API (#31) reads packs from here — persist so the dashboard renders
STATE_DB = "dbre_state"
STATE_COLL = "evidence_packs"


async def run_demo(
    connection_string: str | None = None,
    *,
    backend=None,
    narrator: Narrator | None = None,
    run_id: str = "demo-001",
    created_at: str | None = None,
) -> EvidencePack:
    owns_backend = backend is None
    if owns_backend:
        backend = PymongoBackend(connection_string, DB, COLL)  # pragma: no cover - live
    try:
        return await run_remediation(
            backend,
            run_id=run_id,
            namespace=f"{DB}.{COLL}",
            query_filter=QUERY_FILTER,
            query_sort=QUERY_SORT,
            limit=LIMIT,
            created_at=created_at,
            narrator=narrator,
        )
    finally:
        if owns_backend:
            backend.close()  # pragma: no cover - live


def main() -> None:  # pragma: no cover - live entrypoint
    from dotenv import load_dotenv

    from controller.narrate import GeminiNarrator

    load_dotenv()
    conn = os.environ.get("MDB_MCP_CONNECTION_STRING") or os.environ.get("MONGODB_TARGET_URI")
    if not conn:
        raise SystemExit("no Mongo connection string (set MDB_MCP_CONNECTION_STRING)")
    pack = asyncio.run(run_demo(conn, narrator=GeminiNarrator()))
    path = write_pack(pack, Path("runs"))

    from pymongo import MongoClient

    client = MongoClient(conn)
    try:
        save_pack(client[STATE_DB][STATE_COLL], pack)
    finally:
        client.close()

    print(
        f"DEMO {pack.run_id} status={pack.status} severity={pack.finding.severity} "
        f"before_keys={pack.before.metrics.total_keys_examined} "
        f"after_keys={pack.after.metrics.total_keys_examined if pack.after else None}"
    )
    print(f"narrative: {pack.narrative[:240] if pack.narrative else None}")
    print(f"-> {path}")
    print(f"-> mongo {STATE_DB}.{STATE_COLL} ({pack.run_id})")


if __name__ == "__main__":  # pragma: no cover
    main()
