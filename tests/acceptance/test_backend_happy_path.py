def test_backend_completes_reviewed_dual_approval(workflow_driver) -> None:
    final_state = workflow_driver.complete()

    assert final_state["status"] == "approved"
    assert len(final_state["latestBrief"]["approvals"]) == 2
    assert len(final_state["questions"]) <= 10
    assert not any(
        conflict["status"] == "open" and conflict["severity"] == "critical"
        for conflict in final_state["conflicts"]
    )
    assert any(
        conflict["resolution"] == "Use the lower-cost stone-effect finish."
        for conflict in final_state["conflicts"]
    )
    assert not any(
        conflict["status"] == "open"
        for conflict in final_state["latestBrief"]["payload"]["conflicts"]
    )
    assert final_state["briefSchemaValid"] is True
