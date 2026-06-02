"""Agent eval runner (#38).

Grades the DBRE agent's diagnosis quality on the #9 fixture and emits a scorecard
(JSON + markdown). Two layers:

  * DETERMINISTIC (always runs, CI-safe): the phase gate, plus the deterministic
    `diagnose()` over the known fixture signal — proves the ESR logic recommends
    index C, not B, with no model or network.

  * LIVE (opt-in): triggers the deployed agent via `POST {API_URL}/run` (real
    ADK + Gemini + MCP on Agent Engine), then grades the returned EvidencePack —
    its recommendation, its narrative grounding, and the round-trip latency.
    Skipped unless RUN_API_TOKEN + API_URL are set.

Usage:
    uv run python -m evals.run_eval                 # deterministic only
    # with RUN_API_TOKEN + API_URL in env/.env:
    uv run python -m evals.run_eval --live          # + live graded run

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
from evals.grade import (
    Scorecard,
    grade_esr_correct,
    grade_latency,
    grade_narrative_grounded,
    grade_phase_gate,
)

# The #9 fixture query shape (the preset Denver/ESR demo).
QUERY_FILTER = {"storeLocation": "Denver", "customer.age": {"$gte": 30, "$lte": 50}}
QUERY_SORT = [("saleDate", -1)]

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


def trigger_live_run(api_url: str, token: str, timeout: float = 120.0) -> tuple[dict, float]:
    """POST /run on the deployed read API; return (pack, elapsed_seconds)."""
    req = urllib.request.Request(
        f"{api_url.rstrip('/')}/run",
        data=b"{}",
        headers={"content-type": "application/json", "x-api-token": token},
        method="POST",
    )
    start = time.monotonic()
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (trusted URL)
        pack = json.loads(resp.read())
    return pack, time.monotonic() - start


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

    mode = "+".join(parts)

    write_scorecard(card, mode)
    print(f"[{mode}] {card.summary} -> {'PASS' if card.passed else 'FAIL'}")
    for c in card.checks:
        print(f"  {'PASS' if c.passed else 'FAIL'}  {c.name}: {c.detail}")
    print(f"\nwrote {OUT_JSON.name} + {OUT_MD.name}")
    return 0 if card.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
