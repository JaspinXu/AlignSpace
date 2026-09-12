from alignspace.agents.contracts import AgentResult, AssetRef, VisionProvider
from alignspace.domain.models import ProjectState
from alignspace.domain.patches import StatePatch, UpsertAttribute, apply_patch


class VisionAnalyst:
    def __init__(self, provider: VisionProvider) -> None:
        self._provider = provider

    def run(self, state: ProjectState, assets: list[AssetRef]) -> AgentResult:
        operations = [
            UpsertAttribute(attribute=attribute)
            for attribute in self._provider.analyze(state, assets)
        ]
        if not operations:
            return AgentResult(state=state)
        updated = apply_patch(
            state,
            StatePatch(expected_state_version=state.state_version, operations=operations),
        )
        return AgentResult(state=updated, patches=operations)
