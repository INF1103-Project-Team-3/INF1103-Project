"""GroqClient: sends requests to Groq and turns failures into LLMRequestError."""

import logging

import requests

from .llm_client import LLMClient
from .llm_request_error import LLMRequestError
from .rate_limiter import FALLBACK_DELAY_S, RateLimiter

logger = logging.getLogger(__name__)

API_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "openai/gpt-oss-120b"
REQUEST_TIMEOUT_S = 30


class GroqClient(LLMClient):
    """LLMClient for Groq's chat completions endpoint."""

    def __init__(self, api_key: str | None, model: str | None = None):
        self.__api_key = api_key
        self.__model = model if model is not None else MODEL
        # One shared session, so every request reuses the open connection instead
        # of repeating the TCP/TLS handshake.
        self.__session = requests.Session()
        self.__rate_limiter = RateLimiter()

    @property
    def model(self) -> str:
        return self.__model

    def send(
        self,
        messages: list[dict[str, str]],
        schema_name: str,
        schema: dict,
        token_margin: int,
        max_completion_tokens: int | None = None,
    ) -> tuple[str, int, float]:
        """POST one strict-schema chat completion to Groq. See LLMClient.send."""
        if not self.__api_key:
            raise LLMRequestError("API key missing", LLMRequestError.AUTH, False)
        body = {
            "model": self.__model,
            "messages": messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": schema},
            },
        }
        if max_completion_tokens is not None:
            body["max_completion_tokens"] = max_completion_tokens
        try:
            response = self.__session.post(
                API_URL, headers={"Authorization": f"Bearer {self.__api_key}"}, json=body, timeout=REQUEST_TIMEOUT_S
            )
        except requests.RequestException as exc:
            logger.debug("connection failed: %s", exc)
            raise LLMRequestError("connection failed", LLMRequestError.CONNECTION, True) from exc
        if response.status_code >= 400:
            raise self._to_error(response, token_margin)
        # In its own try, as requests' JSON error is also a RequestException.
        try:
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            total_tokens = (payload.get("usage") or {}).get("total_tokens", 0)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            logger.debug("malformed response: %r", exc)
            raise LLMRequestError("malformed response", LLMRequestError.OUTPUT, True) from exc
        wait_seconds = self.__rate_limiter.compute_delay(response.headers, FALLBACK_DELAY_S, token_margin)
        return content, total_tokens, wait_seconds

    def _to_error(self, response: requests.Response, token_margin: int) -> LLMRequestError:
        """Return the LLMRequestError for a 4xx/5xx response.

        Rate limits (429), Groq capacity (498) and server errors (5xx) are
        temporary. So is a 400 json_validate_failed: the model's output was at
        fault, not the request, and a new attempt usually succeeds. Anything
        else (a bad key, a malformed request) fails the same way every time.
        """
        status = response.status_code
        # The cause (e.g. invalid_request_error) is only in the body.
        logger.debug("HTTP %d response body: %s", status, response.text[:500])
        wait_seconds = self.__rate_limiter.compute_delay(response.headers, None, token_margin)
        if status in (429, 498):
            return LLMRequestError(f"rate limited (HTTP {status})", LLMRequestError.RATE_LIMIT, True, wait_seconds)
        if status >= 500:
            return LLMRequestError(f"server error (HTTP {status})", LLMRequestError.SERVER, True, wait_seconds)
        if status in (401, 403):
            return LLMRequestError(f"key rejected (HTTP {status})", LLMRequestError.AUTH, False)
        if status == 400 and self._is_json_validate_failed(response):
            return LLMRequestError(f"invalid output (HTTP {status})", LLMRequestError.OUTPUT, True, wait_seconds)
        return LLMRequestError(f"request rejected (HTTP {status})", LLMRequestError.REQUEST, False)

    def _is_json_validate_failed(self, response: requests.Response) -> bool:
        """Return True if Groq rejected the model's output against the schema."""
        try:
            return response.json()["error"]["code"] == "json_validate_failed"
        except (ValueError, KeyError, TypeError):
            return False
