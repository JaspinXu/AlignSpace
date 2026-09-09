from pydantic import BaseModel, ValidationError

from alignspace.agents.contracts import LanguageModelProvider


class ProviderOutputError(ValueError):
    """Raised when provider output remains invalid after the repair attempt."""


def generate_validated[ResultModel: BaseModel](
    provider: LanguageModelProvider,
    task: str,
    payload: dict[str, object],
    result_model: type[ResultModel],
) -> ResultModel:
    try:
        return result_model.model_validate(provider.generate(task, payload))
    except ValidationError as first_error:
        repair_payload = {
            **payload,
            "validationErrors": first_error.errors(include_url=False),
        }
        try:
            return result_model.model_validate(provider.generate(f"{task}:repair", repair_payload))
        except ValidationError as second_error:
            raise ProviderOutputError("provider output invalid after two attempts") from second_error
