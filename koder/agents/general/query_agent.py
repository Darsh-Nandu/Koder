"""
query_agent.py

A Query Agent node for LangGraph pipelines.

Behavior:
- Takes the user's raw query + current project state (context dict).
- If the query is clear/simple -> enhances/rewrites it into a more
  detailed, context-aware query (e.g. for retrieval / downstream agents).
- If the query is ambiguous -> instead of enhancing, it generates 2-3
  clarifying "Did you mean X or Y?" style options and routes back to
  the user (sets a flag so your graph can loop back to INPUT).

Usage in LangGraph:

    from query_agent import query_agent_node

    graph.add_node("query_agent", query_agent_node)

State expected (a dict, TypedDict, or pydantic model with attribute access)
should contain at least:
    - "query": str                -> latest user input
    - "project_state": dict/str   -> optional context about the project
    - "conversation_history": list[str]  -> optional, recent turns

After running, the node adds/updates:
    - "enhanced_query": str | None
    - "is_ambiguous": bool
    - "clarification_question": str | None
    - "clarification_options": list[str]
"""

import os
import json
from typing import Any, Dict, List, Optional, TypedDict

from groq import Groq


MODEL_NAME = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """You are a Query Agent inside an AI coding/project assistant pipeline.

Your job: look at the user's latest query, plus the current project state and
recent conversation history, and decide ONE of two things:

1. If the query is CLEAR ENOUGH to act on (even if short), REWRITE it into an
   enhanced, self-contained, detailed query that includes relevant context
   from the project state. This enhanced query will be passed directly to
   downstream agents, so it should be specific and unambiguous.

2. If the query is AMBIGUOUS (could reasonably mean 2+ different things,
   missing key info needed to proceed, vague pronouns/references, etc.),
   DO NOT guess. Instead produce a short clarification question and 2-4
   concrete options phrased like "Did you mean: ... ?" so the user can
   pick one or answer briefly.

Respond ONLY with valid JSON, no markdown, no extra text, in this exact shape:

{
  "is_ambiguous": true | false,
  "enhanced_query": "<string or null>",
  "clarification_question": "<string or null>",
  "clarification_options": ["<option1>", "<option2>", ...] or []
}

Rules:
- If is_ambiguous is true, enhanced_query MUST be null, and
  clarification_question + clarification_options MUST be filled in.
- If is_ambiguous is false, clarification_question and
  clarification_options MUST be null / empty, and enhanced_query MUST be
  a non-empty, improved version of the query.
- Keep clarification_options short and mutually exclusive (max ~4).
- Be conservative: only flag ambiguity if it would genuinely change the
  approach/answer. Simple, direct requests should NOT be flagged.
"""


class QueryAgentState(TypedDict, total=False):
    query: str
    project_state: Any
    conversation_history: List[str]
    enhanced_query: Optional[str]
    is_ambiguous: bool
    clarification_question: Optional[str]
    clarification_options: List[str]


def _get_client() -> Groq:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY environment variable not set. "
            "Set it before running the query agent."
        )
    return Groq(api_key=api_key)


def _format_project_state(project_state: Any) -> str:
    if project_state is None:
        return "No project state provided."
    if isinstance(project_state, str):
        return project_state
    try:
        return json.dumps(project_state, indent=2, default=str)
    except TypeError:
        return str(project_state)


def _format_history(history: Optional[List[str]]) -> str:
    if not history:
        return "No prior conversation history."
    # Only keep the last few turns to keep prompt small
    recent = history[-6:]
    return "\n".join(f"- {turn}" for turn in recent)


def analyze_query(
    query: str,
    project_state: Any = None,
    conversation_history: Optional[List[str]] = None,
    model: str = MODEL_NAME,
    temperature: float = 0.2,
) -> Dict[str, Any]:
    """
    Core logic: call Groq to classify the query as ambiguous or not,
    and either enhance it or generate clarification options.

    Returns a dict matching the JSON shape described in SYSTEM_PROMPT.
    """
    client = _get_client()

    user_prompt = f"""User query: "{query}"

Project state:
{_format_project_state(project_state)}

Recent conversation history:
{_format_history(conversation_history)}

Analyze the query as instructed and respond with the JSON object only."""

    response = client.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: treat as non-ambiguous, pass query through unchanged
        result = {
            "is_ambiguous": False,
            "enhanced_query": query,
            "clarification_question": None,
            "clarification_options": [],
        }

    # Normalize/validate shape
    is_ambiguous = bool(result.get("is_ambiguous", False))
    enhanced_query = result.get("enhanced_query")
    clarification_question = result.get("clarification_question")
    clarification_options = result.get("clarification_options") or []

    if is_ambiguous:
        enhanced_query = None
        if not clarification_question:
            clarification_question = "Could you clarify what you mean?"
    else:
        clarification_question = None
        clarification_options = []
        if not enhanced_query:
            enhanced_query = query  # fallback, don't drop the query

    return {
        "is_ambiguous": is_ambiguous,
        "enhanced_query": enhanced_query,
        "clarification_question": clarification_question,
        "clarification_options": clarification_options,
    }


def query_agent_node(state: QueryAgentState) -> QueryAgentState:
    """
    LangGraph node entrypoint.

    Reads `state["query"]`, `state.get("project_state")`,
    `state.get("conversation_history")`, runs analysis, and merges
    the result fields back into the state dict.

    Use the returned `is_ambiguous` flag in your graph's conditional
    edges to route back to the INPUT node (to ask the user the
    clarification question) or forward to the next agent with
    `enhanced_query`.
    """
    query = state.get("query", "")
    if not query or not query.strip():
        return {
            **state,
            "is_ambiguous": True,
            "enhanced_query": None,
            "clarification_question": "I didn't receive a query — what would you like help with?",
            "clarification_options": [],
        }

    result = analyze_query(
        query=query,
        project_state=state.get("project_state"),
        conversation_history=state.get("conversation_history"),
    )

    return {**state, **result}


if __name__ == "__main__":
    # Simple manual test / CLI usage
    print("Query Agent (Groq) — type 'exit' to quit\n")

    project_state_example = {
        "project_name": "data-quality-kit",
        "current_focus": "Adding drift detection module and Plotly dashboard",
        "recent_files_changed": ["drift.py", "dashboard.py", "README.md"],
    }

    history: List[str] = []

    while True:
        q = input("You: ").strip()
        if q.lower() in {"exit", "quit"}:
            break

        state: QueryAgentState = {
            "query": q,
            "project_state": project_state_example,
            "conversation_history": history,
        }

        out = query_agent_node(state)

        if out["is_ambiguous"]:
            print(f"\n[Query Agent] {out['clarification_question']}")
            for i, opt in enumerate(out["clarification_options"], 1):
                print(f"  {i}. {opt}")
            print()
        else:
            print(f"\n[Query Agent] Enhanced query:\n{out['enhanced_query']}\n")

        history.append(f"User: {q}")