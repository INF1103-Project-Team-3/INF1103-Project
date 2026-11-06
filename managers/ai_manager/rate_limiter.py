"""RateLimiter: works out the wait before the next request from Groq's headers."""

import re
from collections.abc import Mapping

# Groq's binding limit is 8000 tokens per minute, so the wait before the next
# request is read from the retry-after and x-ratelimit-* response headers.
MIN_DELAY_S = 0.5  # wait while the token budget is healthy
FALLBACK_DELAY_S = 2.7  # wait when a response carries no rate-limit headers
DELAY_BUFFER_S = 0.25  # added to header-derived waits so the reset has passed
# (?!s) stops the "m" of a millisecond value such as "250ms" reading as minutes.
RESET_DURATION_RE = re.compile(r"(?:(\d+)h)?(?:(\d+)m(?!s))?(?:([\d.]+)s)?(?:([\d.]+)ms)?")


class RateLimiter:
    """Turns rate-limit response headers into a delay."""

    def parse_reset_duration(self, value: str) -> float:
        """Convert a Groq reset header such as "11.317s", "25m55.199s" or "250ms" to seconds."""
        # Every group is optional, so match() always succeeds; unknown text gives 0.
        match = RESET_DURATION_RE.match(value)
        assert match is not None  # states that invariant for type checkers
        hours, minutes, seconds, millis = match.groups()
        return int(hours or 0) * 3600 + int(minutes or 0) * 60 + float(seconds or 0) + float(millis or 0) / 1000

    def compute_delay(self, headers: Mapping[str, str], fallback: float | None, margin: int) -> float | None:
        """Return the seconds to wait before the next request, from rate-limit headers.

        Honours retry-after if present; otherwise waits for the token reset once
        fewer than margin tokens remain. Returns fallback if the headers are
        missing or malformed.
        """
        try:
            retry_after = headers.get("retry-after")
            if retry_after is not None:
                return float(retry_after) + DELAY_BUFFER_S
            remaining = headers.get("x-ratelimit-remaining-tokens")
            reset = headers.get("x-ratelimit-reset-tokens")
            if remaining is None or reset is None:
                return fallback
            if int(remaining) < margin:
                return self.parse_reset_duration(reset) + DELAY_BUFFER_S
            return MIN_DELAY_S
        except ValueError:
            return fallback
