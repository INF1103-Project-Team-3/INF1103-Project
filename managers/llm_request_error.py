"""LLMRequestError: a failed LLM request, and what the caller can do about it."""


class LLMRequestError(Exception):
    """One failed request: why it failed, whether to retry and how long to wait first."""

    CONNECTION = "connection"
    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    SERVER = "server"
    OUTPUT = "output"
    REQUEST = "request"

    def __init__(self, message: str, kind: str, retryable: bool, wait_seconds: float | None = None):
        super().__init__(message)
        self.__kind = kind
        self.__retryable = retryable
        self.__wait_seconds = wait_seconds

    @property
    def kind(self) -> str:
        return self.__kind

    @property
    def retryable(self) -> bool:
        return self.__retryable

    @property
    def wait_seconds(self) -> float | None:
        """Seconds to wait before retrying; None means the caller uses its backoff."""
        return self.__wait_seconds
