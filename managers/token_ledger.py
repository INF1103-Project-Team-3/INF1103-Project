"""TokenLedger: a local daily log of tokens used, with a warning near the daily cap."""

import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

TPD_LIMITS = {"openai/gpt-oss-120b": 200_000}
TPD_WARNING_THRESHOLD = 0.8


class TokenLedger:
    """Groq reports the daily cap (TPD) only in a 429 once it is hit, so a local
    ledger of each response's usage.total_tokens gives early warning. It is an
    estimate and undercounts: a failed attempt returns no usage, though Groq may
    still bill it. Groq's own count (the console) is authoritative.
    """

    def __init__(self, model: str, path: str):
        self.__model = model
        self.__path = path
        self.__usage_label = f"groq/{model}"  # same key the comparison harness used

    def record(self, key_label: str, request_id: str, total_tokens: int) -> None:
        """Add one request's token usage to the ledger, warning near the daily cap.

        Keyed by UTC date (approximating Groq's sliding daily window), then by
        key_label, because the cap applies per API key. Same schema as the
        comparison harness's ledger. total_tokens covers only attempts that
        returned usage; a request whose every attempt failed is still recorded,
        with 0. Ledger problems are logged, never raised, since tracking is
        advisory.
        """
        try:
            with open(self.__path, encoding="utf-8") as file:
                log = json.load(file)
        except FileNotFoundError:
            log = {}
        except (OSError, json.JSONDecodeError) as exc:
            # Never overwrite a ledger that failed to load.
            logger.warning("token ledger unreadable, usage not recorded: %s", exc)
            return

        today = datetime.now(timezone.utc).date().isoformat()
        key_log = log.setdefault(today, {}).setdefault(key_label, {})
        totals = key_log.setdefault("totals", {})
        usage = key_log.setdefault("candidates", {}).setdefault(
            self.__usage_label, {"model": self.__model, "total_tokens": 0, "requests": []}
        )
        before = totals.get(self.__model, 0)
        if total_tokens > 0:
            totals[self.__model] = before + total_tokens
        # "feedback_id" is the harness's key name; it holds any request_id.
        usage["requests"].append({"feedback_id": request_id, "total_tokens": total_tokens})
        usage["total_tokens"] += total_tokens

        try:
            with open(self.__path, "w", encoding="utf-8") as file:
                json.dump(log, file, indent=2)
        except OSError as exc:
            logger.warning("token ledger not written: %s", exc)
            return
        self._warn_if_near_cap(before, before + total_tokens)

    def _warn_if_near_cap(self, before: int, after: int) -> None:
        """Log a warning when a request takes the model past the daily-cap threshold."""
        limit = TPD_LIMITS.get(self.__model)
        if limit is None:
            return
        threshold = limit * TPD_WARNING_THRESHOLD
        if before < threshold <= after:
            logger.warning(
                "%s has crossed %.0f%% of its known ~%d daily token budget (%d/%d used today, local estimate)",
                self.__model, TPD_WARNING_THRESHOLD * 100, limit, after, limit,
            )
