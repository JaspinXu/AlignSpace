from alignspace.providers.mock import build_mock_agents
from alignspace.workflow.runtime import memory_graph, sqlite_graph


def test_graph_starts_with_vision_and_pauses_for_homeowner() -> None:
    graph = memory_graph(build_mock_agents())
    config = {"configurable": {"thread_id": "project-1"}}

    result = graph.invoke({"project_id": "project-1"}, config=config)

    assert result["project_state"]["attributes"]
    assert result["__interrupt__"][0].value["waitReason"] == "homeowner"
    assert result["pending_question"]["targetRole"] == "homeowner"


def test_graph_defines_every_required_node_including_explicit_stop() -> None:
    graph = memory_graph(build_mock_agents())

    assert {
        "vision_analysis",
        "homeowner_interview",
        "wait_homeowner",
        "designer_review",
        "wait_designer",
        "alignment",
        "wait_professional",
        "draft_brief",
        "review",
        "awaiting_approval",
        "stop_unresolved",
    } <= set(graph.get_graph().nodes)


def test_sqlite_graph_persists_an_interrupt_checkpoint(tmp_path) -> None:
    checkpoint_path = tmp_path / "workflow.db"
    graph = sqlite_graph(build_mock_agents(), str(checkpoint_path))
    config = {"configurable": {"thread_id": "project-sqlite"}}

    result = graph.invoke({"project_id": "project-sqlite"}, config=config)

    assert result["__interrupt__"][0].value["waitReason"] == "homeowner"
    assert checkpoint_path.exists()
