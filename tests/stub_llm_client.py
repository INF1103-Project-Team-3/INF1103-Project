"""StubLLMClient: an LLMClient that plays back scripted replies, with no network."""

from llm_client import LLMClient
from llm_request_error import LLMRequestError


class StubLLMClient(LLMClient):
    """Each reply is the content to return, or an LLMRequestError to raise."""

    def __init__(self, replies: list[str | LLMRequestError], tokens: int = 100, wait_seconds: float = 0.5):
        self.__replies = list(replies)
        self.__tokens = tokens
        self.__wait_seconds = wait_seconds
        self.__calls = []

    @property
    def model(self) -> str:
        return "stub-model"

    @property
    def calls(self) -> list[dict]:
        """The arguments of every send so far."""
        return list(self.__calls)

    def send(self, messages, schema_name, schema, token_margin, max_completion_tokens=None):
        self.__calls.append({
            "messages": messages,
            "schema_name": schema_name,
            "schema": schema,
            "token_margin": token_margin,
            "max_completion_tokens": max_completion_tokens,
        })
        reply = self.__replies.pop(0)
        if isinstance(reply, LLMRequestError):
            raise reply
        return reply, self.__tokens, self.__wait_seconds
