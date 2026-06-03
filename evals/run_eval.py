"""Agent eval runner (#38).

Grades the DBRE agent's diagnosis quality on the #9 fixture and emits a scorecard
(JSON + markdown). Two layers:

  * DETERMINISTIC (always runs, CI-safe): the phase gate, plus the deterministic
    `diagnose()` over the known fixture signal — proves the ESR logic recommends
    index C, not B, with no model or network.

  * LIVE (opt-in): triggers the deployed agent via `POST {API_URL}/run` (real
    Agent Engine + deterministic controller), then grades the returned EvidencePack —
    its recommendation, its narrative grounding, and the round-trip latency.
    Skipped unless RUN_API_TOKEN + API_URL are set.

  * DIAGRAM-LIVE (opt-in): triggers `/run`, approves the returned pack, inspects
    Mongo ledger records and target indexes, and grades the intended architecture
    properties end to end.

Usage:
    uv run python -m evals.run_eval                 # deterministic only
    # with RUN_API_TOKEN + API_URL in env/.env:
    uv run python -m evals.run_eval --live          # + live graded run
    uv run python -m evals.run_eval --diagram-live  # + architecture gate

Outputs: evals/scorecard.json, evals/scorecard.md
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from controller.diagnosis import diagnose
from controller.explain import get_connection_string
from evals.grade import (
    Scorecard,
    grade_agent_engine_used,
    grade_approval_gate_first,
    grade_approval_gate_records,
    grade_approval_verified,
    grade_esr_correct,
    grade_ledger_records,
    grade_latency,
    grade_narrative_grounded,
    grade_no_extra_indexes,
    grade_no_mutation_before_approval,
    grade_phase_gate,
    grade_tokenless_writes_rejected,
)

# The #9 fixture query shape (the preset Denver/ESR demo).
QUERY_FILTER = {"storeLocation": "Denver", "customer.age": {"$gte": 30, "$lte": 50}}
QUERY_SORT = [("saleDate", -1)]
TARGET_DB = "sample_supplies"
TARGET_COLL = "sales_agent_demo"
STATE_DB = "dbre_state"

OUT_JSON = Path(__file__).parent / "scorecard.json"
OUT_MD = Path(__file__).parent / "scorecard.md"


def grade_deterministic(card: Scorecard) -> None:
    """Model-free, network-free checks — always run."""
    # ESR logic: feed the known blocking-sort signal, confirm it recommends C.
    diagnosis = diagnose(
        QUERY_FILTER, QUERY_SORT, has_blocking_sort=True, current_index="esr_wrong_B"
    )
    card.checks.append(grade_esr_correct(diagnosis.recommendation.index_spec))
    card.checks.append(grade_phase_gate())


def trigger_live_run(
    api_url: str, token: str, timeout: float = 120.0, run_id: str | None = None
) -> tuple[dict, float]:
    """POST /run on the deployed read API; return (pack, elapsed_seconds)."""
    body = {} if run_id is None else {"run_id": run_id}
    req = urllib.request.Request(
        f"{api_url.rstrip('/')}/run",
        data=json.dumps(body).encode(),
        headers={"content-type": "application/json", "x-api-token": token},
        method="POST",
    )
    start = time.monotonic()
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (trusted URL)
        pack = json.loads(resp.read())
    return pack, time.monotonic() - start


def submit_approval(api_url: str, token: str, run_id: str, evidence_hash: str) -> dict:
    payload = {
        "decision": "approve",
        "evidence_hash": evidence_hash,
        "approver": "eval-diagram",
        "note": "diagram conformance eval",
    }
    req = urllib.request.Request(
        f"{api_url.rstrip('/')}/packs/{run_id}/decision",
        data=json.dumps(payload).encode(),
        headers={"content-type": "application/json", "x-api-token": token},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310 (trusted URL)
        return json.loads(resp.read())


def post_without_token(api_url: str, path: str, payload: dict) -> int:
    req = urllib.request.Request(
        f"{api_url.rstrip('/')}{path}",
        data=json.dumps(payload).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (trusted URL)
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


def grade_live(card: Scorecard, api_url: str, token: str) -> dict | None:
    """Trigger the real agent and grade the returned pack. Returns the pack."""
    try:
        pack, elapsed = trigger_live_run(api_url, token)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        card.add("live_run", False, f"POST /run failed: {exc}")
        return None

    card.add("live_run", True, f"POST /run returned status={pack.get('status')}")
    rec = pack.get("recommendation", {})
    card.checks.append(grade_esr_correct(rec.get("index_spec", [])))
    card.checks.append(grade_narrative_grounded(pack.get("narrative")))
    card.checks.append(grade_latency(elapsed))
    return pack


def _ledger_record_ids(run_id: str) -> dict[str, tuple[str, str]]:
    return {
        "slow_queries": ("slow_queries", f"{run_id}:diagnose:slow_query"),
        "candidates": ("candidates", f"{run_id}:diagnose:candidate"),
        "experiments": ("experiments", f"{run_id}:diagnose:before"),
        "gate_opened": ("approvals", f"{run_id}:gate:opened"),
        "gate_pending": ("approvals", f"{run_id}:gate:pending"),
        "decisions": ("decisions", f"{run_id}:approve:decision"),
        "evidence_packs": ("evidence_packs", run_id),
        "approvals": ("approvals", f"{run_id}:approve:approval"),
        "applications": ("applications", f"{run_id}:approve:application"),
        "verifications": ("verifications", f"{run_id}:verify:verification"),
    }


def grade_diagram_live(card: Scorecard, api_url: str, token: str, connection_string: str) -> None:
    """Live diagram-conformance check: /run is read-only, approval mutates/verifies,
    Agent Engine participates, ledger records exist, and target indexes stay clean."""
    from pymongo import MongoClient

    run_id = f"eval-diagram-{int(time.time())}"
    client = MongoClient(connection_string)
    target = client[TARGET_DB][TARGET_COLL]
    state = client[STATE_DB]

    def indexes() -> set[str]:
        return {index["name"] for index in target.list_indexes()}

    try:
        before_indexes = indexes()
        diagnosed, elapsed = trigger_live_run(api_url, token, timeout=300, run_id=run_id)
        after_run_indexes = indexes()
        verified = submit_approval(api_url, token, run_id, diagnosed["evidence_hash"])
        after_approve_indexes = indexes()
        ids = _ledger_record_ids(run_id)
        records = {
            logical_name: doc
            for logical_name, (collection, record_id) in ids.items()
            if (doc := state[collection].find_one({"_id": record_id}, projection={"_id": False}))
            is not None
        }
        present = {ids[logical_name][0] for logical_name in records}
        source_records = {
            collection: records[collection]
            for collection in ("slow_queries", "candidates", "experiments")
            if collection in records
        }
        tokenless_run = post_without_token(api_url, "/run", {"run_id": f"{run_id}-no-token"})
        tokenless_decision = post_without_token(
            api_url,
            f"/packs/{run_id}/decision",
            {"decision": "approve", "evidence_hash": diagnosed["evidence_hash"]},
        )
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError) as exc:
        card.add("diagram_live", False, f"diagram live check failed: {exc}")
        return
    finally:
        client.close()

    card.add("diagram_live", True, f"completed run_id={run_id}")
    card.checks.append(grade_approval_gate_first(diagnosed))
    card.checks.append(grade_agent_engine_used(diagnosed))
    card.checks.append(grade_no_mutation_before_approval(before_indexes, after_run_indexes))
    card.checks.append(grade_approval_gate_records(records))
    card.checks.append(grade_ledger_records(present, source_records))
    card.checks.append(grade_approval_verified(diagnosed, verified))
    card.checks.append(grade_no_extra_indexes(after_approve_indexes))
    card.checks.append(grade_tokenless_writes_rejected(tokenless_run, tokenless_decision))
    card.checks.append(grade_latency(elapsed))


def grade_demo_pack(card: Scorecard, api_url: str, pack_id: str = "demo-001") -> dict | None:
    """Grade the pre-seeded demo pack, which carries a REAL Gemini narrative — this is
    where the anti-hallucination (narrative_grounded) check meets real model output.
    Read-only: no token needed."""
    try:
        with urllib.request.urlopen(  # noqa: S310 (trusted URL)
            f"{api_url.rstrip('/')}/packs/{pack_id}", timeout=30
        ) as resp:
            pack = json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        card.add("demo_pack", False, f"GET /packs/{pack_id} failed: {exc}")
        return None

    card.add("demo_pack", True, f"loaded {pack_id} (Gemini narrative present)")
    card.checks.append(grade_esr_correct(pack.get("recommendation", {}).get("index_spec", [])))
    card.checks.append(grade_narrative_grounded(pack.get("narrative")))
    return pack


def write_scorecard(card: Scorecard, mode: str) -> None:
    payload = {
        "mode": mode,
        "summary": card.summary,
        "passed": card.passed,
        "checks": [{"name": c.name, "passed": c.passed, "detail": c.detail} for c in card.checks],
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2) + "\n")

    lines = [
        "# Agent eval scorecard (#38)",
        "",
        f"**Mode:** {mode}  ·  **Result:** {card.summary}  ·  "
        f"**{'PASS' if card.passed else 'FAIL'}**",
        "",
        "| Check | Result | Detail |",
        "|-------|--------|--------|",
    ]
    for c in card.checks:
        mark = "✅" if c.passed else "❌"
        lines.append(f"| `{c.name}` | {mark} | {c.detail} |")
    lines.append("")
    OUT_MD.write_text("\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser(description="Grade the DBRE agent on the #9 fixture.")
    ap.add_argument("--live", action="store_true", help="also trigger + grade a live agent run")
    ap.add_argument(
        "--demo-pack",
        action="store_true",
        help="also grade the pre-seeded demo-001 pack's real Gemini narrative (read-only)",
    )
    ap.add_argument(
        "--diagram-live",
        action="store_true",
        help="run the live diagram-conformance gate: /run, approval, ledger, indexes",
    )
    args = ap.parse_args()

    api_url = os.environ.get("API_URL") or os.environ.get("NEXT_PUBLIC_API_URL")

    card = Scorecard()
    grade_deterministic(card)
    parts = ["deterministic"]

    if args.demo_pack:
        if not api_url:
            card.add("demo_pack", False, "skipped: API_URL not set")
        else:
            parts.append("demo-pack")
            grade_demo_pack(card, api_url)

    if args.live:
        token = os.environ.get("RUN_API_TOKEN")
        if not (api_url and token):
            card.add("live_run", False, "skipped: API_URL / RUN_API_TOKEN not set")
        else:
            parts.append("live")
            grade_live(card, api_url, token)

    if args.diagram_live:
        token = os.environ.get("RUN_API_TOKEN")
        connection_string = get_connection_string()
        if not (api_url and token and connection_string):
            card.add(
                "diagram_live",
                False,
                "skipped: API_URL / RUN_API_TOKEN / Mongo connection string not set",
            )
        else:
            parts.append("diagram-live")
            grade_diagram_live(card, api_url, token, connection_string)

    mode = "+".join(parts)

    write_scorecard(card, mode)
    print(f"[{mode}] {card.summary} -> {'PASS' if card.passed else 'FAIL'}")
    for c in card.checks:
        print(f"  {'PASS' if c.passed else 'FAIL'}  {c.name}: {c.detail}")
    print(f"\nwrote {OUT_JSON.name} + {OUT_MD.name}")
    return 0 if card.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
