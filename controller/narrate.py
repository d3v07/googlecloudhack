"""Gemini narration layer — turns a deterministic EvidencePack into an SRE-facing narrative.

The deterministic decision (finding, recommendation, evidence_hash) stays authoritative.
Gemini only explains; it never alters the pack's structural fields.
"""

import os
from typing import Protocol

from controller.schemas import EvidencePack


def build_narration_prompt(pack: EvidencePack) -> str:
    before_keys = pack.before.metrics.total_keys_examined
    before_sort = pack.before.metrics.has_blocking_sort
    index_spec_str = ", ".join(
        f"{field} {'ASC' if direction == 1 else 'DESC'}"
        for field, direction in pack.recommendation.index_spec
    )

    after_lines: list[str] = []
    if pack.after is not None:
        after_keys = pack.after.metrics.total_keys_examined
        after_sort = pack.after.metrics.has_blocking_sort
        after_lines = [
            f"- After index: total_keys_examined={after_keys}, has_blocking_sort={after_sort}",
        ]

    after_section = "\n".join(after_lines) if after_lines else "- After index: not yet measured"

    return (
        "You are an SRE assistant. Explain the following MongoDB query performance finding "
        "in plain English (3–5 sentences). Base your explanation ONLY on the numbers and "
        "facts provided below — do not invent data.\n\n"
        "## Observed performance (before recommended index)\n"
        f"- total_keys_examined: {before_keys}\n"
        f"- has_blocking_sort: {before_sort}\n"
        f"- problem: {pack.finding.problem}\n\n"
        "## After applying recommended index\n"
        f"{after_section}\n\n"
        "## Recommended index\n"
        f"- index_spec: [{index_spec_str}]\n"
        f"- rationale: {pack.recommendation.rationale}\n\n"
        "Explain why the query was slow and why this index fixes it, "
        "citing the specific numbers above."
    )


class Narrator(Protocol):
    def narrate(self, pack: EvidencePack) -> str:
        """Return a human-facing narrative for the given pack."""


class GeminiNarrator:
    def __init__(self) -> None:
        self._model = os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview")

    def narrate(self, pack: EvidencePack) -> str:  # pragma: no cover
        from google import genai
        from google.genai import types

        project = os.environ["GOOGLE_CLOUD_PROJECT"]
        client = genai.Client(vertexai=True, project=project, location="global")
        response = client.models.generate_content(
            model=self._model,
            contents=build_narration_prompt(pack),
            config=types.GenerateContentConfig(
                max_output_tokens=512,
                temperature=0.2,
                thinking_config=types.ThinkingConfig(thinking_level="minimal"),
            ),
        )
        if response.text:
            return response.text
        parts = []
        for candidate in response.candidates or []:
            content = candidate.content
            for part in content.parts if content and content.parts else []:
                if part.text:
                    parts.append(part.text)
        return "\n".join(parts)
