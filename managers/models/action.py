"""Action: something an admin did about a theme, so its impact can be measured."""

from datetime import datetime
from typing import Self

from .serializable import Serializable


class Action(Serializable):
    """A logged action. Created once by I/O or the GUI and never changed;
    its impact result is a separate ImpactReport from Logic."""

    def __init__(
        self,
        action_id: str,
        theme: str,
        description: str,
        action_date: str,
        keyword: str | None,
        logged_at: str,
    ):
        """Raises ValueError for empty text, a date that is not YYYY-MM-DD,
        or a keyword that is not text. A blank keyword becomes None."""
        for name, value in (("action_id", action_id), ("theme", theme),
                            ("description", description), ("logged_at", logged_at)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty text, got {value!r}")
        if not self.__is_date(action_date):
            raise ValueError(f"action_date must be a real date as YYYY-MM-DD, got {action_date!r}")
        if keyword is not None:
            if not isinstance(keyword, str):
                raise ValueError(f"keyword must be text or None, got {keyword!r}")
            # a blank keyword box means "measure all feedback on this theme"
            keyword = keyword.strip() or None

        self.__action_id = action_id
        self.__theme = theme
        self.__description = description
        self.__action_date = action_date
        self.__keyword = keyword
        self.__logged_at = logged_at

    @property
    def action_id(self) -> str:
        return self.__action_id

    @property
    def theme(self) -> str:
        """A known theme (base or confirmed)."""
        return self.__theme

    @property
    def description(self) -> str:
        return self.__description

    @property
    def action_date(self) -> str:
        """When the action happened, YYYY-MM-DD. May be in the future."""
        return self.__action_date

    @property
    def keyword(self) -> str | None:
        """Only feedback containing this word is measured; None measures the whole theme."""
        return self.__keyword

    @property
    def logged_at(self) -> str:
        """When the admin logged it."""
        return self.__logged_at

    def to_dict(self) -> dict:
        return {
            "action_id": self.__action_id,
            "theme": self.__theme,
            "description": self.__description,
            "action_date": self.__action_date,
            "keyword": self.__keyword,
            "logged_at": self.__logged_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        """Rebuilds an action saved by to_dict(). Raises KeyError for a missing
        field or ValueError for a bad value, so Data can skip a corrupt entry."""
        return cls(data["action_id"], data["theme"], data["description"],
                   data["action_date"], data.get("keyword"), data["logged_at"])

    def __repr__(self) -> str:
        return f"Action({self.__action_id!r}, {self.__theme!r}, {self.__action_date!r})"

    @staticmethod
    def __is_date(text) -> bool:
        """True only for a real calendar date written exactly as YYYY-MM-DD."""
        try:
            return datetime.strptime(text, "%Y-%m-%d").strftime("%Y-%m-%d") == text
        except (TypeError, ValueError):
            return False
