"""Probe Gemini 3 access on Vertex AI.

Run:
uv run --with google-genai --with python-dotenv python spikes/day1_gemini3/probe.py
"""

import os

from dotenv import load_dotenv

load_dotenv()

from google import genai
from google.genai import types

MODEL_IDS = (
    "gemini-3-flash-preview",
    "gemini-3-pro-preview",
)


def _locations() -> tuple[str, str]:
    default_location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    if default_location == "global":
        return ("global",)
    return (default_location, "global")


def _snippet(text: str) -> str:
    return " ".join(text.split())[:160]


def _thinking_config(model_id: str) -> types.ThinkingConfig:
    level = "minimal" if "flash" in model_id else "low"
    return types.ThinkingConfig(thinking_level=level)


def _response_text(response) -> str:
    if response.text:
        return response.text
    parts = []
    for candidate in response.candidates or []:
        content = candidate.content
        for part in content.parts if content and content.parts else []:
            if part.text:
                parts.append(part.text)
    return "\n".join(parts)


def probe_model(model_id: str, location: str) -> None:
    project = os.environ["GOOGLE_CLOUD_PROJECT"]
    client = genai.Client(vertexai=True, project=project, location=location)
    try:
        response = client.models.generate_content(
            model=model_id,
            contents="Reply with exactly: gemini3-ok",
            config=types.GenerateContentConfig(
                max_output_tokens=64,
                temperature=0,
                thinking_config=_thinking_config(model_id),
            ),
        )
        text = _response_text(response)
        if text:
            print(f"PASS model={model_id} location={location} text={_snippet(text)}")
        else:
            print(f"FAIL model={model_id} location={location} error=empty response text")
    except Exception as exc:
        print(f"FAIL model={model_id} location={location} error={type(exc).__name__}: {exc}")


def main() -> None:
    print(f"PROJECT={os.environ.get('GOOGLE_CLOUD_PROJECT', '<missing>')}")
    print(f"DEFAULT_LOCATION={os.environ.get('GOOGLE_CLOUD_LOCATION', '<missing>')}")
    print("DOCS_MODEL_IDS=gemini-3-flash-preview,gemini-3-pro-preview")
    for model_id in MODEL_IDS:
        for location in _locations():
            probe_model(model_id, location)


if __name__ == "__main__":
    main()
