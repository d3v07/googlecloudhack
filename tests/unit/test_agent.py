import pickle

from agents.agent import AgentRole, build_agent
from agents.agent_engine_factory import build_adk_app
from controller.phases import Phase


def test_agent_builds_with_diagnose_tool_and_a_gate():
    agent = build_agent(Phase.DIAGNOSE)

    tool_names = [getattr(tool, "name", None) for tool in agent.tools]
    assert "explain_slow_query" in tool_names
    assert "compare_candidate_indexes" in tool_names
    assert "diagnose_candidate" in tool_names
    assert "rationalize_recommendation" in tool_names
    assert "diagnose_index" in tool_names
    assert callable(agent.before_tool_callback)
    assert agent.name == "dbre_full_agent"


def test_split_agents_expose_only_their_role_tools():
    diagnose_tools = {
        getattr(tool, "name", None) for tool in build_agent(role=AgentRole.DIAGNOSE).tools
    }
    candidate_tools = {
        getattr(tool, "name", None) for tool in build_agent(role=AgentRole.CANDIDATE).tools
    }
    rationale_tools = {
        getattr(tool, "name", None) for tool in build_agent(role=AgentRole.RATIONALE).tools
    }

    assert diagnose_tools == {"explain_slow_query", "diagnose_candidate"}
    assert candidate_tools == {"compare_candidate_indexes"}
    assert rationale_tools == {"rationalize_recommendation"}


def test_agent_gate_reflects_the_phase():
    class _Tool:
        name = "create-index"

    diagnose_agent = build_agent(Phase.DIAGNOSE)
    verify_agent = build_agent(Phase.VERIFY)

    assert diagnose_agent.before_tool_callback(_Tool(), {}, None)["blocked"] is True
    assert verify_agent.before_tool_callback(_Tool(), {}, None) is None


def test_agent_engine_app_is_pickleable_for_object_deploy():
    app = build_adk_app()

    restored = pickle.loads(pickle.dumps(app))

    assert hasattr(restored, "async_stream_query")
    assert hasattr(restored, "stream_query")
