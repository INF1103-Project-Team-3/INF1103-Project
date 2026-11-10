"""RecordValidator: checks records before Logic uses them."""

from datetime import datetime

from managers.models import REVIEWED, SENTIMENTS, SEVERITIES, VERIFICATION, FeedbackRecord


class RecordValidator:
    """Splits records into valid and invalid. One bad record never stops the
    rest, and each invalid record keeps the reasons it failed."""

    __TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S"

    def validate(self, records) -> tuple[list[FeedbackRecord], list[tuple[FeedbackRecord, list[str]]]]:
        """Returns (valid, invalid), where invalid is a list of (record, problems)."""
        valid, invalid = [], []
        seen_ids = set()
        for record in records:
            problems = self.__problems(record)
            if not problems:
                # a repeated id would be counted twice; the first one is kept
                if record.feedback_id in seen_ids:
                    problems.append(f"duplicate feedback_id '{record.feedback_id}'")
                seen_ids.add(record.feedback_id)
            if problems:
                invalid.append((record, problems))
            else:
                valid.append(record)
        return valid, invalid

    def __problems(self, record) -> list[str]:
        """Every problem with one record; an empty list means it is valid."""
        if not isinstance(record, FeedbackRecord):
            return [f"not a FeedbackRecord, got {type(record).__name__}"]
        problems = []
        for field, value in (("feedback_id", record.feedback_id), ("text", record.text)):
            if not self.__is_text(value):
                problems.append(f"'{field}' must be non-empty text, got {value!r}")
        if not self.__is_timestamp(record.timestamp):
            problems.append(f"'timestamp' must be YYYY-MM-DDTHH:MM:SS, got {record.timestamp!r}")
        problems += self.__value_problems("user", record.user)
        if record.ai is not None:
            problems += self.__value_problems("ai", record.ai)
        if record.verification not in VERIFICATION:
            problems.append(f"'verification' must be one of {list(VERIFICATION)}, got {record.verification!r}")
        elif record.verification == REVIEWED:
            # the rules skip reviewed records, so the admin's values are used exactly as saved
            final = {"theme": record.theme, "sentiment": record.sentiment, "severity": record.severity}
            problems += self.__value_problems("final", final)
        return problems

    def __value_problems(self, name: str, values: dict) -> list[str]:
        """Problems with one set of theme, sentiment and severity."""
        problems = []
        theme, sentiment, severity = values.get("theme"), values.get("sentiment"), values.get("severity")
        if not self.__is_text(theme):
            problems.append(f"{name} theme must be non-empty text, got {theme!r}")
        if sentiment not in SENTIMENTS:
            problems.append(f"{name} sentiment must be one of {list(SENTIMENTS)}, got {sentiment!r}")
        if severity not in SEVERITIES:
            problems.append(f"{name} severity must be one of {list(SEVERITIES)}, got {severity!r}")
        return problems

    @staticmethod
    def __is_text(value) -> bool:
        return isinstance(value, str) and bool(value.strip())

    def __is_timestamp(self, value) -> bool:
        """True only for a real date and time written exactly as YYYY-MM-DDTHH:MM:SS."""
        try:
            parsed = datetime.strptime(value, self.__TIMESTAMP_FORMAT)
        except (TypeError, ValueError):
            return False
        return parsed.strftime(self.__TIMESTAMP_FORMAT) == value
