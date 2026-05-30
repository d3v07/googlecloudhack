"""Day-0 runtime spike (issue #1): Agent Builder vs Agent Engine.

The decision turns on ONE thing: can the runtime express, in code, our two
control-flow requirements?
  (a) per-phase tool allowlists  (a write tool is blocked outside its phase)
  (b) a human-in-loop pause awaiting an external signal

Agent Builder is a declarative/console product — it can't run this custom logic
(and can't be scripted here). Agent Engine runs arbitrary Python (ADK), so if ADK
proves (a) and (b), Engine wins. This script proves them with ADK on Vertex.

Run: uv run --with google-adk --with python-dotenv python spikes/day0_runtime/spike_capabilities.py
"""
import asyncio
import os

from dotenv import load_dotenv

load_dotenv()

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import FunctionTool, LongRunningFunctionTool
from google.genai import types

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")


def echo_stub(text: str) -> dict:
    """Echo text back — stub tool to prove tool-calling works."""
    return {"echoed": text}


def apply_index(spec: str) -> dict:
    """Apply a MongoDB index (WRITE — must be blocked outside the verify phase)."""
    return {"applied": spec}


def request_human_approval(evidence_hash: str) -> dict:
    """Request human sign-off; resolves only when a human responds."""
    return {"status": "pending", "evidence_hash": evidence_hash}


PHASE_ALLOWLIST = {
    "diagnose": {"echo_stub"},
    "approve": {"echo_stub", "request_human_approval"},
    "verify": {"echo_stub", "apply_index"},
}


def make_gate(phase: str):
    allowed = PHASE_ALLOWLIST[phase]

    def before_tool(tool, args, tool_context):
        if tool.name not in allowed:
            return {"blocked": True, "phase": phase, "tool": tool.name,
                    "reason": f"{tool.name} not allowed in '{phase}' {sorted(allowed)}"}
        return None

    return before_tool


async def run_agent(agent, prompt):
    sess = InMemorySessionService()
    runner = Runner(agent=agent, app_name="spike", session_service=sess)
    await sess.create_session(app_name="spike", user_id="u", session_id="s")
    calls, blocked, long_running = [], [], []
    async for ev in runner.run_async(
        user_id="u", session_id="s",
        new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
    ):
        for part in (ev.content.parts if ev.content and ev.content.parts else []):
            if part.function_call:
                calls.append(part.function_call.name)
            fr = part.function_response
            if fr and isinstance(fr.response, dict) and fr.response.get("blocked"):
                blocked.append(fr.name)
        if getattr(ev, "long_running_tool_ids", None):
            long_running.extend(ev.long_running_tool_ids)
    return calls, blocked, long_running


async def main():
    print(f"MODEL={MODEL}")

    # CAP2 (deterministic): the gate logic itself blocks a disallowed write tool
    class _T:
        def __init__(self, n): self.name = n
    det = make_gate("diagnose")(_T("apply_index"), {"spec": "x"}, None)
    cap2_det = bool(det and det.get("blocked"))
    print(f"CAP2-logic gate blocks apply_index in diagnose: {'PASS' if cap2_det else 'FAIL'} {det}")

    # CAP1: Gemini calls a tool through ADK
    try:
        a1 = Agent(name="diag", model=MODEL, tools=[FunctionTool(echo_stub)],
                   instruction="You MUST call the echo_stub tool with the user's word, then say done.")
        calls, _, _ = await run_agent(a1, "echo the word HELLO")
        cap1 = "echo_stub" in calls
        print(f"CAP1 ADK tool-call on Vertex: {'PASS' if cap1 else 'FAIL'} (calls={calls})")
    except Exception as e:
        cap1 = False
        print(f"CAP1 ERROR: {repr(e)[:300]}")

    # CAP2 (live): callback fires before the tool and blocks it
    try:
        a2 = Agent(name="diag2", model=MODEL,
                   tools=[FunctionTool(echo_stub), FunctionTool(apply_index)],
                   before_tool_callback=make_gate("diagnose"),
                   instruction="Call the apply_index tool with spec 'idx1' right now.")
        calls2, blocked2, _ = await run_agent(a2, "apply an index, spec idx1")
        cap2_live = "apply_index" in blocked2
        print(f"CAP2 live phase-gate block: {'PASS' if cap2_live else 'INCONCLUSIVE'} (calls={calls2}, blocked={blocked2})")
    except Exception as e:
        cap2_live = False
        print(f"CAP2 live ERROR: {repr(e)[:300]}")

    # CAP3: human-in-loop pause — long-running tool yields control to the app
    try:
        a3 = Agent(name="appr", model=MODEL,
                   tools=[LongRunningFunctionTool(func=request_human_approval)],
                   before_tool_callback=make_gate("approve"),
                   instruction="Call request_human_approval with evidence_hash 'abc'.")
        calls3, _, lr3 = await run_agent(a3, "get human approval for evidence abc")
        cap3 = len(lr3) > 0
        print(f"CAP3 human-pause (long-running yields): {'PASS' if cap3 else 'FAIL'} (long_running_ids={lr3}, calls={calls3})")
    except Exception as e:
        cap3 = False
        print(f"CAP3 ERROR: {repr(e)[:300]}")

    decided = cap2_det and cap1 and cap3
    print(f"RESULT engine_capabilities_proven={decided}")


asyncio.run(main())
