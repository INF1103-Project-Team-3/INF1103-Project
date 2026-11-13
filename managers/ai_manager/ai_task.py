"""AITask: one kind of LLM request, independent of the provider and the retry loop."""

import copy
import json
from abc import ABC, abstractmethod


class AITask(ABC):
    """Abstract: what to send, and how to check what comes back."""

    def __init__(
        self,
        request_id: str,
        schema_name: str,
        schema: dict,
        token_margin: int,
        max_completion_tokens: int | None = None,
    ):
        self.__request_id = request_id
        self.__schema_name = schema_name
        self.__schema = schema
        self.__token_margin = token_margin
        self.__max_completion_tokens = max_completion_tokens

    @property
    def request_id(self) -> str:
        """This request's name in logs and the token ledger."""
        return self.__request_id

    @property
    def schema_name(self) -> str:
        return self.__schema_name

    @property
    def schema(self) -> dict:
        """A copy, so a caller cannot change what validation checks against."""
        return copy.deepcopy(self.__schema)

    @property
    def token_margin(self) -> int:
        return self.__token_margin

    @property
    def max_completion_tokens(self) -> int | None:
        return self.__max_completion_tokens

    @abstractmethod
    def build_messages(self) -> list[dict[str, str]]:
        """Return the chat messages for this request."""

    @abstractmethod
    def validate(self, result: object) -> bool:
        """Return True if result is valid output for this task."""

    def parse(self, raw: str) -> dict | None:
        """Return the validated output, or None if it fails validation.

        Raises json.JSONDecodeError or TypeError if raw is not JSON text.
        """
        result = self._clean(json.loads(raw))
        return result if self.validate(result) else None

    def _clean(self, result: object) -> object:
        """Return result tidied before validation. Most tasks need nothing here."""
        return result
