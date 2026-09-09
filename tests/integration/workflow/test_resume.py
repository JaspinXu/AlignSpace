from langgraph.types import Command

from alignspace.providers.mock import build_mock_agents
from alignspace.workflow.runtime import memory_graph


def test_homeowner_answer_resumes_same_thread() -> None:
    graph = memory_graph(build_mock_agents())
    config = {"configurable": {"thread_id": "project-1"}}
    graph.invoke({"project_id": "project-1"}, config=config)

    resumed = graph.invoke(
        Command(resume={"answer": "I also like the warm lighting"}),
        config=config,
    )

    assert resumed["project_state"]["stateVersion"] >= 1
    broad = next(
        question
        for question in resumed["project_state"]["questions"]
        if question["repetitionFingerprint"] == "liked-elements"
    )
    assert broad["answer"] == "I also like the warm lighting"
    assert resumed["__interrupt__"][0].value["waitReason"] == "homeowner"


def test_different_thread_does_not_resume_existing_interrupt() -> None:
    graph = memory_graph(build_mock_agents())
    first_config = {"configurable": {"thread_id": "project-1"}}
    second_config = {"configurable": {"thread_id": "project-2"}}
    graph.invoke({"project_id": "project-1"}, config=first_config)

    second = graph.invoke({"project_id": "project-2"}, config=second_config)

    assert second["project_id"] == "project-2"
    assert second["project_state"]["projectId"] == "project-2"
