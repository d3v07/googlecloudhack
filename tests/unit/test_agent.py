from agents.agent import build_agent
from controller.phases import Phase


def test_agent_builds_with_diagnose_tool_and_a_gate():
    agent = build_agent(Phase.DIAGNOSE)

    tool_names = [getattr(tool, "name", None) for tool in agent.tools]
    assert "diagnose_index" in tool_names
    assert callable(agent.before_tool_callback)
    assert agent.name == "dbre_agent"


def test_agent_gate_reflects_the_phase():
    class _Tool:
        name = "create-index"

    diagnose_agent = build_agent(Phase.DIAGNOSE)
    verify_agent = build_agent(Phase.VERIFY)

    assert diagnose_agent.before_tool_callback(_Tool(), {}, None)["blocked"] is True
    assert verify_agent.before_tool_callback(_Tool(), {}, None) is None
