import os

from google.adk.agents import Agent

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

root_agent = Agent(
    name="gcrah_deploy_probe",
    model=MODEL,
    instruction=(
        "You are a minimal deployment probe for the GCRAH project. "
        "Answer with one concise sentence that starts with 'deploy-ok'."
    ),
)
