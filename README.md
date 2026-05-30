# googlecloudhack — Evidence-Driven DBRE Agent

A Gemini-powered MongoDB performance engineer: detects slow queries, proposes indexes with
*predicted* plan changes, benchmarks candidates, and gates `apply` behind human approval —
shipping a hashed evidence pack for every fix.

> **Status:** Day-0 — scaffold + runtime decision landed.

## Architecture

Five demo stages (Detect → Diagnose → Test → Approve → Verify) over a seven-phase engine.

**Runtime: Vertex AI Agent Engine + ADK.** Agent Builder's declarative model can't express our
per-phase tool allowlists or human-in-loop approval pause; Agent Engine runs the custom ADK Python
that does both — proven on Day 0 by the scripts in [`spikes/day0_runtime/`](spikes/day0_runtime/).

## Quickstart

```bash
uv sync --dev
cp .env.example .env   # fill GCP + MongoDB values
uv run pytest -q
```

## License

Apache-2.0 — see [`LICENSE`](LICENSE).
