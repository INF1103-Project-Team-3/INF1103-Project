"""PromptLibrary: loads and checks the theme list and system prompts."""

import json
import os

CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")
PROMPT_PATH = os.path.join(CONFIG_DIR, "system_prompt.txt")
THEMES_PATH = os.path.join(CONFIG_DIR, "themes.json")
THEMES_PLACEHOLDER = "{themes}"
SUMMARY_PROMPT_PATH = os.path.join(CONFIG_DIR, "summary_prompt.txt")
UNCLEAR_THEME = "Unclear"


class PromptLibrary:
    """The themes and prompts for one run, loaded when created.

    Raises ValueError if a file holds bad config.
    """

    def __init__(
        self,
        themes_path: str = THEMES_PATH,
        prompt_path: str = PROMPT_PATH,
        summary_prompt_path: str = SUMMARY_PROMPT_PATH,
    ):
        self.__themes = self._load_themes(themes_path)
        self.__system_prompt = self._load_system_prompt(prompt_path)
        self.__summary_prompt = self._load_summary_prompt(summary_prompt_path)

    @property
    def themes(self) -> list[str]:
        """The canonical theme list."""
        return list(self.__themes)

    @property
    def system_prompt(self) -> str:
        """The call 1 system prompt, with its {themes} placeholder filled in."""
        return self.__system_prompt

    @property
    def summary_prompt(self) -> str:
        """The call 2 system prompt."""
        return self.__summary_prompt

    def find_new_themes(self, records: list[dict], known_themes: list[str] | None = None) -> list[str]:
        """Return known_themes extended with any labels the model coined in records.

        Call once with the stored records to seed the list, then once per new
        record, so a coined label is offered back to the model across runs.
        Reads ai_theme only, so human tags never reach the model. First-seen
        order keeps the payload stable between runs.
        """
        new_themes = list(known_themes or [])
        for record in records:
            theme = record.get("ai_theme") if isinstance(record, dict) else None
            if theme and theme != UNCLEAR_THEME and theme not in self.__themes and theme not in new_themes:
                new_themes.append(theme)
        return new_themes

    def _load_themes(self, path: str) -> list[str]:
        """Return the canonical theme list.

        Raises ValueError if the file is not a non-empty list of theme names.
        """
        with open(path, encoding="utf-8") as file:
            themes = json.load(file)
        if not isinstance(themes, list) or not themes or not all(isinstance(t, str) and t for t in themes):
            raise ValueError(f"{path} must be a non-empty JSON list of theme names")
        return themes

    def _load_system_prompt(self, path: str) -> str:
        """Return the system prompt with its {themes} placeholder filled in.

        Raises ValueError unless the template contains the placeholder exactly once.
        """
        with open(path, encoding="utf-8") as file:
            template = file.read().strip()
        if template.count(THEMES_PLACEHOLDER) != 1:
            raise ValueError(f"{path} must contain {THEMES_PLACEHOLDER} exactly once")
        # str.replace, not str.format: the prompt's JSON examples contain braces.
        return template.replace(THEMES_PLACEHOLDER, ", ".join(self.__themes))

    def _load_summary_prompt(self, path: str) -> str:
        """Return the call 2 system prompt.

        Raises ValueError if the file is empty.
        """
        with open(path, encoding="utf-8") as file:
            prompt = file.read().strip()
        if not prompt:
            raise ValueError(f"{path} is empty")
        return prompt
