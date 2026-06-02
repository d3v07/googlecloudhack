"""Agent eval harness (#38): runs the ADK + Gemini DBRE agent against the #9
fixture and grades its diagnosis quality. Lives outside controller/agents/api —
it exercises and scores them, never reaches into their internals."""
