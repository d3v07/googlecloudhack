"""Phase-gated tool allowlist. The agent may read in any phase, but index WRITES
(`create-index` / `drop-index`) are only permitted in the verify phase — a write can
never run during diagnosis or while awaiting approval. Returning a dict from an ADK
`before_tool_callback` short-circuits the tool, so a blocked write never executes.
"""

from collections.abc import Mapping

from controller.phases import Phase

_READ_TOOLS = frozenset(
    {
        "explain",
        "find",
        "aggregate",
        "count",
        "collection-schema",
        "collection-indexes",
        "list-databases",
        "list-collections",
        "diagnose_index",
    }
)
_WRITE_TOOLS = frozenset({"create-index", "drop-index"})

PHASE_ALLOWLIST: Mapping[Phase, frozenset[str]] = {
    Phase.DIAGNOSE: _READ_TOOLS,
    Phase.APPROVE: _READ_TOOLS,
    Phase.VERIFY: _READ_TOOLS | _WRITE_TOOLS,
}


def is_allowed(phase: Phase, tool_name: str) -> bool:
    return tool_name in PHASE_ALLOWLIST[phase]


def make_gate(phase: Phase):
    allowed = PHASE_ALLOWLIST[phase]

    def before_tool_callback(tool, args, tool_context):
        if tool.name not in allowed:
            return {
                "blocked": True,
                "phase": phase.value,
                "tool": tool.name,
                "reason": f"{tool.name} is not allowed in the '{phase.value}' phase",
            }
        return None

    return before_tool_callback
