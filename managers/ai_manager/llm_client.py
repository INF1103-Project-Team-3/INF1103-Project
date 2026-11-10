"""LLMClient: what AIManager needs from any LLM provider."""

from abc import ABC, abstractmethod


class LLMClient(ABC):
    """Interface: must be able to send one structured request."""

    @property
    @abstractmethod
    def model(self) -> str:
        """The model name, which the token ledger is keyed by."""

    @abstractmethod
    def send(
        self,
        messages: list[dict[str, str]],
        schema_name: str,
        schema: dict,
        token_margin: int,
        max_completion_tokens: int | None = None,
    ) -> tuple[str, int, float]:
        """Send one strict-schema chat completion.

        token_margin is how many tokens must remain before the next request
        goes without waiting for the reset. max_completion_tokens caps output,
        reasoning included; None keeps the provider's default. Returns
        (content, total_tokens, wait_seconds), where content is the model's
        output as a JSON string. Raises LLMRequestError on failure.
        """
