"""AI manager: every LLM API call goes through here.

Call 1 (classify_entry) classifies one feedback entry. The request, retry,
rate-limit and token-tracking plumbing is shared so call 2 (summarise) can
reuse it. API only: no print(), no domain rules. Procedural, no classes.
"""

import json
import logging
import os
import re
import time
from collections import Counter
from collections.abc import Callable, Mapping
from datetime import datetime, timezone

import requests

logger = logging.getLogger(__name__)

# --- Config files ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROMPT_PATH = os.path.join(BASE_DIR, "config", "system_prompt.txt")
THEMES_PATH = os.path.join(BASE_DIR, "config", "themes.json")
THEMES_PLACEHOLDER = "{themes}"

# --- API ---
API_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "openai/gpt-oss-120b"
REQUEST_TIMEOUT_S = 30
MAX_ATTEMPTS = 3  # per request, covering schema mismatches and API failures
MAX_SUMMARY_WORDS = 15
# Each entry is classified this many times so run-to-run instability is
# measured (the agreement field) rather than hidden. Triples token use.
SAMPLES_PER_ENTRY = 3
CLASSIFIED_FIELDS = ("theme", "sentiment", "severity")
# One shared session, so every request reuses the open connection instead of
# repeating the TCP/TLS handshake.
HTTP_SESSION = requests.Session()

# --- Rate limiting ---
# Groq's binding limit is 8000 tokens per minute, so the wait before the next
# request is read from the retry-after and x-ratelimit-* response headers.
MIN_DELAY_S = 0.5  # wait while the token budget is healthy
FALLBACK_DELAY_S = 2.7  # wait when a response carries no rate-limit headers
DELAY_BUFFER_S = 0.25  # added to header-derived waits so the reset has passed
BACKOFF_BASE_S = 2  # failed attempt n waits BACKOFF_BASE_S ** n without headers
# Wait for the reset once fewer tokens than this remain. Kept at the tested
# value, although measured call 1 requests average ~1,700 tokens (max 2,295).
TOKEN_SAFETY_MARGIN = 1600
# (?!s) stops the "m" of a millisecond value such as "250ms" reading as minutes.
RESET_DURATION_RE = re.compile(r"(?:(\d+)h)?(?:(\d+)m(?!s))?(?:([\d.]+)s)?(?:([\d.]+)ms)?")

# --- Daily token ledger ---
# Groq reports the daily cap (TPD) only in a 429 once it is hit, so a local
# ledger of each response's usage.total_tokens gives early warning. It is an
# estimate; Groq's own count is authoritative.
TOKEN_USAGE_LOG_PATH = os.path.join(BASE_DIR, "config", "token-usage-log.json")
TOKEN_USAGE_LABEL = f"groq/{MODEL}"  # same key the comparison harness used
TPD_LIMITS = {"openai/gpt-oss-120b": 200_000}
TPD_WARNING_THRESHOLD = 0.8

# Dict, not a Pydantic BaseModel, to respect the no-class rule. Strict mode
# requires every property in "required" and additionalProperties: false.
CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "theme": {"type": "string"},
        "sentiment": {"type": "string", "enum": ["positive", "neutral", "negative"]},
        "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
        "summary": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["theme", "sentiment", "severity", "summary", "confidence"],
    "additionalProperties": False,
}


# --- Prompt and themes ---

def load_canonical_themes(path: str = THEMES_PATH) -> list[str]:
    """Return the canonical theme list.

    Raises ValueError if the file is not a non-empty list of theme names.
    """
    with open(path, encoding="utf-8") as file:
        themes = json.load(file)
    if not isinstance(themes, list) or not themes or not all(isinstance(t, str) and t for t in themes):
        raise ValueError(f"{path} must be a non-empty JSON list of theme names")
    return themes


def load_system_prompt(canonical_themes: list[str], path: str = PROMPT_PATH) -> str:
    """Return the system prompt with its {themes} placeholder filled in.

    Raises ValueError unless the template contains the placeholder exactly once.
    """
    with open(path, encoding="utf-8") as file:
        template = file.read().strip()
    if template.count(THEMES_PLACEHOLDER) != 1:
        raise ValueError(f"{path} must contain {THEMES_PLACEHOLDER} exactly once")
    # str.replace, not str.format: the prompt's JSON examples contain braces.
    return template.replace(THEMES_PLACEHOLDER, ", ".join(canonical_themes))


def find_new_themes(
    records: list[dict], canonical_themes: list[str], known_themes: list[str] | None = None
) -> list[str]:
    """Return known_themes extended with any non-canonical themes in records.

    Call once with the stored records to seed the list, then once per new
    record, so a coined label is offered back to the model across runs.
    First-seen order keeps the payload stable between runs.
    """
    new_themes = list(known_themes or [])
    for record in records:
        theme = record.get("theme")
        if theme and theme not in canonical_themes and theme not in new_themes:
            new_themes.append(theme)
    return new_themes


# --- Request building ---

def build_user_payload(entry: dict[str, str], known_themes: list[str]) -> dict:
    """Return the user message payload: the feedback text, plus coined themes if any."""
    payload = {"text": entry["text"]}
    if known_themes:  # omitted when empty, to avoid paying for an empty list
        payload["existing_new_themes"] = known_themes
    return payload


def build_messages(
    entry: dict[str, str], system_prompt: str, known_themes: list[str]
) -> list[dict[str, str]]:
    """Return the chat messages for one classification request.

    json.dumps stops the feedback text breaking the payload structure;
    instructions written inside the text are handled by the prompt.
    """
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(build_user_payload(entry, known_themes))},
    ]


# --- Transport and rate limiting ---

def parse_reset_duration(value: str) -> float:
    """Convert a Groq reset header such as "11.317s", "25m55.199s" or "250ms" to seconds."""
    # Every group is optional, so match() always succeeds; unknown text gives 0.
    hours, minutes, seconds, millis = RESET_DURATION_RE.match(value).groups()
    return int(hours or 0) * 3600 + int(minutes or 0) * 60 + float(seconds or 0) + float(millis or 0) / 1000


def compute_delay(headers: Mapping[str, str], fallback: float, margin: int = TOKEN_SAFETY_MARGIN) -> float:
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
            return parse_reset_duration(reset) + DELAY_BUFFER_S
        return MIN_DELAY_S
    except ValueError:
        return fallback


def call_api(
    messages: list[dict[str, str]], schema_name: str, schema: dict, api_key: str
) -> tuple[str, Mapping[str, str], int]:
    """POST one strict-schema chat completion to Groq.

    Returns (content, headers, total_tokens), where content is the model's
    output as a JSON string. Raises requests.HTTPError on 4xx/5xx (including
    429), another requests.RequestException on network failure, and
    KeyError/IndexError/TypeError if choices[0].message.content is missing.
    """
    body = {
        "model": MODEL,
        "messages": messages,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "strict": True, "schema": schema},
        },
    }
    response = HTTP_SESSION.post(
        API_URL, headers={"Authorization": f"Bearer {api_key}"}, json=body, timeout=REQUEST_TIMEOUT_S
    )
    response.raise_for_status()
    payload = response.json()
    content = payload["choices"][0]["message"]["content"]
    total_tokens = (payload.get("usage") or {}).get("total_tokens", 0)
    # response.headers is kept case-insensitive for compute_delay's lookups.
    return content, response.headers, total_tokens


def validate_classification(result: object) -> bool:
    """Return True if result is a valid five-field classification.

    Strict mode guarantees the shape but not the confidence range or the
    summary word limit, which its schema subset cannot express.
    """
    props = CLASSIFY_SCHEMA["properties"]
    return (
        isinstance(result, dict)
        and set(result) == set(CLASSIFY_SCHEMA["required"])
        and result["sentiment"] in props["sentiment"]["enum"]
        and result["severity"] in props["severity"]["enum"]
        and isinstance(result["confidence"], (int, float))
        and 0.0 <= result["confidence"] <= 1.0
        and isinstance(result["summary"], str)
        and len(result["summary"].split()) <= MAX_SUMMARY_WORDS
    )


# --- Token ledger ---

def maybe_warn_token_budget(model: str, before: int, after: int) -> None:
    """Log a warning when a request takes the model past the daily-cap threshold."""
    limit = TPD_LIMITS.get(model)
    if limit is None:
        return
    threshold = limit * TPD_WARNING_THRESHOLD
    if before < threshold <= after:
        logger.warning(
            "%s has crossed %.0f%% of its known ~%d daily token budget (%d/%d used today, local estimate)",
            model, TPD_WARNING_THRESHOLD * 100, limit, after, limit,
        )


def record_token_usage(key_label: str, request_id: str, total_tokens: int) -> None:
    """Add one request's token usage to the ledger, warning near the daily cap.

    Keyed by UTC date (approximating Groq's sliding daily window), then by
    key_label, because the cap applies per API key. Same schema as the
    comparison harness's ledger. Ledger problems are logged, never raised,
    since tracking is advisory.
    """
    try:
        with open(TOKEN_USAGE_LOG_PATH, encoding="utf-8") as file:
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
        TOKEN_USAGE_LABEL, {"model": MODEL, "total_tokens": 0, "requests": []}
    )
    before = totals.get(MODEL, 0)
    if total_tokens > 0:
        totals[MODEL] = before + total_tokens
    # "feedback_id" is the harness's key name; it holds any request_id.
    usage["requests"].append({"feedback_id": request_id, "total_tokens": total_tokens})
    usage["total_tokens"] += total_tokens

    try:
        with open(TOKEN_USAGE_LOG_PATH, "w", encoding="utf-8") as file:
            json.dump(log, file, indent=2)
    except OSError as exc:
        logger.warning("token ledger not written: %s", exc)
        return
    maybe_warn_token_budget(MODEL, before, before + total_tokens)


# --- Requests ---

def request_structured_output(
    messages: list[dict[str, str]],
    schema_name: str,
    schema: dict,
    validate: Callable[[object], bool],
    api_key: str,
    key_label: str,
    request_id: str,
    margin: int = TOKEN_SAFETY_MARGIN,
) -> dict | None:
    """Send a request until its output validates, up to MAX_ATTEMPTS times.

    Shared by call 1 and call 2. Every attempt, successful or not, is
    followed by the wait the rate-limit headers call for, so callers never
    need their own throttle. Returns the validated output, or None if every
    attempt failed.
    """
    result = None
    total_tokens = 0
    for attempt in range(1, MAX_ATTEMPTS + 1):
        backoff = BACKOFF_BASE_S**attempt
        try:
            raw, headers, tokens = call_api(messages, schema_name, schema, api_key)
            total_tokens += tokens
            delay = compute_delay(headers, FALLBACK_DELAY_S, margin)
            parsed = json.loads(raw)
            if validate(parsed):
                result = parsed
            else:
                logger.warning("schema mismatch %s attempt %d", request_id, attempt)
        except requests.HTTPError as exc:
            logger.warning("http error %s attempt %d: %s", request_id, attempt, exc)
            delay = backoff
            if exc.response is not None:
                if exc.response.status_code != 429:
                    # The cause (e.g. invalid_request_error) is only in the body.
                    logger.warning("response body: %s", exc.response.text[:500])
                delay = compute_delay(exc.response.headers, backoff, margin)
        except (requests.RequestException, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            # Network failure, a non-JSON body or content, or a missing content path.
            logger.warning("api error %s attempt %d: %s", request_id, attempt, exc)
            delay = backoff
        time.sleep(delay)
        if result is not None:
            break

    record_token_usage(key_label, request_id, total_tokens)
    if result is None:
        logger.error("skipped %s after %d attempts", request_id, MAX_ATTEMPTS)
    return result


# --- Call 1 ---

def majority_or_first(values: list[str]) -> str:
    """Return the value most samples share, or the first sample's if none has a majority."""
    value, count = Counter(values).most_common(1)[0]
    return value if count > len(values) / 2 else values[0]


def aggregate_samples(samples: list[dict]) -> dict:
    """Combine repeated classifications of one entry into one result.

    Theme, sentiment and severity each take the majority value, falling back
    to the first sample's (confidence does not track correctness, so it is
    not used as a tie-breaker). Summary and confidence come from the
    highest-confidence sample that agrees with all three final values.
    agreement is the weakest field's share of samples matching its final
    value: 1.0 means unanimous; logic_manager decides what to flag.
    """
    final = {field: majority_or_first([s[field] for s in samples]) for field in CLASSIFIED_FIELDS}
    agreeing = [s for s in samples if all(s[f] == final[f] for f in CLASSIFIED_FIELDS)]
    source = max(agreeing or samples, key=lambda s: s["confidence"])
    agreement = min(
        sum(s[field] == final[field] for s in samples) / len(samples) for field in CLASSIFIED_FIELDS
    )
    return {**final, "summary": source["summary"], "confidence": source["confidence"],
            "agreement": round(agreement, 2)}


def classify_entry(
    entry: dict[str, str],
    system_prompt: str,
    api_key: str,
    key_label: str,
    known_themes: list[str] | None = None,
) -> dict | None:
    """Classify one feedback entry (call 1), SAMPLES_PER_ENTRY times.

    entry is {"feedback_id", "text", "timestamp"} from io_manager. Returns
    entry merged with the five AI fields plus agreement, or None if any
    sample fails; the caller skips it and it is retried on the next run.
    """
    messages = build_messages(entry, system_prompt, known_themes or [])
    samples = []
    for sample in range(1, SAMPLES_PER_ENTRY + 1):
        result = request_structured_output(
            messages, "feedback_classification", CLASSIFY_SCHEMA, validate_classification,
            api_key, key_label, entry["feedback_id"],
        )
        if result is None:
            # Agreement is only meaningful over the full set of samples.
            logger.error("skipped %s: sample %d of %d failed", entry["feedback_id"], sample, SAMPLES_PER_ENTRY)
            return None
        samples.append(result)
    return {**entry, **aggregate_samples(samples)}
