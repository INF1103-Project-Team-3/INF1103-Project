"""PromptLibrary: checks and holds the theme list and system prompts."""

from managers.models import FeedbackRecord, UNCLEAR_THEME

THEMES_PLACEHOLDER = "{themes}"


class PromptLibrary:
    """The themes and prompts for one run. Reads no files: AppEngine passes them in.

    Raises ValueError if any of them is bad config.
    """

    def __init__(self, system_template: str, summary_prompt: str, themes: list[str]):
        self.__template = system_template
        self.__themes = self._check_themes(themes)
        self.__system_prompt = self._fill_system_prompt(system_template)
        self.__summary_prompt = self._check_summary_prompt(summary_prompt)

    @property
    def themes(self) -> list[str]:
        """The known themes."""
        return list(self.__themes)

    @property
    def system_prompt(self) -> str:
        """The call 1 system prompt, with its {themes} placeholder filled in."""
        return self.__system_prompt

    @property
    def summary_prompt(self) -> str:
        """The call 2 system prompt."""
        return self.__summary_prompt

    def set_themes(self, themes: list[str]) -> None:
        """Replace the known themes and refill the call 1 system prompt.

        Raises ValueError, keeping the old themes, unless themes is a non-empty
        list of names.
        """
        self.__themes = self._check_themes(themes)
        self.__system_prompt = self._fill_system_prompt(self.__template)

    def find_new_themes(self, records: list[FeedbackRecord], known_themes: list[str] | None = None) -> list[str]:
        """Return known_themes extended with any labels the model coined in records.

        Call once with the stored records to seed the list, then once per new
        record, so a coined label is offered back to the model across runs.
        Reads record.ai only, so user values never reach the model. First-seen
        order keeps the payload stable between runs.
        """
        new_themes = list(known_themes or [])
        for record in records:
            # from_dict restores values unchecked, so a saved ai may have no theme.
            theme = (record.ai or {}).get("theme")
            if theme and theme != UNCLEAR_THEME and theme not in self.__themes and theme not in new_themes:
                new_themes.append(theme)
        return new_themes

    def _check_themes(self, themes: list[str]) -> list[str]:
        """Return themes as a list. Raises ValueError unless it is a non-empty list of names."""
        if not isinstance(themes, (list, tuple)) or not themes or not all(isinstance(t, str) and t for t in themes):
            raise ValueError("themes must be a non-empty list of theme names")
        return list(themes)

    def _fill_system_prompt(self, template: str) -> str:
        """Return the system prompt with its {themes} placeholder filled in.

        Raises ValueError unless the template contains the placeholder exactly once.
        """
        template = template.strip()
        if template.count(THEMES_PLACEHOLDER) != 1:
            raise ValueError(f"the system prompt must contain {THEMES_PLACEHOLDER} exactly once")
        # str.replace, not str.format: the prompt's JSON examples contain braces.
        return template.replace(THEMES_PLACEHOLDER, ", ".join(self.__themes))

    def _check_summary_prompt(self, prompt: str) -> str:
        """Return the call 2 system prompt. Raises ValueError if it is empty."""
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("the summary prompt is empty")
        return prompt
