from langgraph.graph import END, START, StateGraph

from backend.agents import demo
from backend.agents import live
from backend.config import get_settings
from backend.graph.state import ContentStudioState


def understand_request(state: ContentStudioState) -> dict:
    return {"planner": demo.plan(state["request"])}


def retrieve_research(state: ContentStudioState) -> dict:
    settings = get_settings()
    if not state["planner"].requires_research:
        return {"research_sources": []}
    if not settings.search_api_key:
        raise RuntimeError("Research is required, but SEARCH_API_KEY is not configured")
    return {"research_sources": live.search_web(state["request"].topic, settings.search_api_key)}


def generate_candidate_angles(state: ContentStudioState) -> dict:
    settings = get_settings()
    if settings.openai_api_key:
        return {"candidate_angles": live.generate_angles(state["request"], state.get("research_sources", []), settings.openai_api_key, settings.openai_model)}
    return {"candidate_angles": demo.generate_angles(state["request"])}


def write_content(state: ContentStudioState) -> dict:
    settings = get_settings()
    draft = live.write_post(state["request"], state["selected_angle"], state.get("research_sources", []), settings.openai_api_key, settings.openai_model) if settings.openai_api_key else demo.write_post(state["request"], state["selected_angle"])
    return {"current_draft": draft, "draft_versions": [draft], "revision_count": 0}


def critique_content(state: ContentStudioState) -> dict:
    settings = get_settings()
    result = live.critique_post(state["current_draft"], state["request"], settings.openai_api_key, settings.openai_model) if settings.openai_api_key else demo.critique(state["current_draft"])
    return {"critique": result}


def revise_content(state: ContentStudioState) -> dict:
    settings = get_settings()
    draft = live.revise_post(state["current_draft"], state["critique"], state["request"], state.get("research_sources", []), settings.openai_api_key, settings.openai_model) if settings.openai_api_key else state["current_draft"] + "\n\nA useful next step is to test this in one bounded workflow."
    return {"current_draft": draft, "draft_versions": [*state["draft_versions"], draft], "revision_count": state["revision_count"] + 1}


def route_after_critique(state: ContentStudioState) -> str:
    if state["critique"].overall < state["quality_threshold"] and state["revision_count"] < state["max_revisions"]:
        return "revise_post"
    return END


strategy_builder = StateGraph(ContentStudioState)
strategy_builder.add_node("understand_request", understand_request)
strategy_builder.add_node("retrieve_research", retrieve_research)
strategy_builder.add_node("generate_angles", generate_candidate_angles)
strategy_builder.add_edge(START, "understand_request")
strategy_builder.add_edge("understand_request", "retrieve_research")
strategy_builder.add_edge("retrieve_research", "generate_angles")
strategy_builder.add_edge("generate_angles", END)
strategy_graph = strategy_builder.compile()

post_builder = StateGraph(ContentStudioState)
post_builder.add_node("write_post", write_content)
post_builder.add_node("critique_post", critique_content)
post_builder.add_node("revise_post", revise_content)
post_builder.add_edge(START, "write_post")
post_builder.add_edge("write_post", "critique_post")
post_builder.add_conditional_edges("critique_post", route_after_critique)
post_builder.add_edge("revise_post", "critique_post")
post_graph = post_builder.compile()
