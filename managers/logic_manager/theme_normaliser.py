"""ThemeNormaliser: gives every theme label one spelling, so the same issue lands in one bucket."""

from managers.models import THEMES, UNCLEAR_THEME


class ThemeNormaliser:
    """Maps a label to a base theme, a confirmed new theme, "Unclear", or a
    cleaned new theme (design reference 7.4)."""

    # Base theme -> other labels the user or the AI might use for it. Labels
    # are compared after cleaning (see __key), so case and punctuation don't
    # matter. To support a new variant, add it to the right list.
    __ALIASES_BY_THEME = {
        "Teaching Quality": [
            "teaching quality", "teaching", "teaching style", "teaching methods",
            "lecture quality", "lectures", "lecture delivery", "lecturer",
            "lecturers", "lecture speed", "lecture pace", "pacing", "pace",
            "course pace", "tutorial quality", "tutorials", "instructor quality",
            "instruction quality", "course content", "module content",
            "teaching staff", "professor quality",
        ],
        "Assessment": [
            "assessment", "assessments", "assignments", "assignment",
            "grading", "marking", "marking criteria", "grading criteria",
            "rubric", "rubrics", "exams", "exam", "examinations", "tests",
            "quizzes", "coursework", "group project grading", "academic integrity",
            "plagiarism",
        ],
        "Facilities": [
            "facilities", "facility", "campus facilities", "infrastructure",
            "equipment", "classrooms", "lecture theatre", "lecture theater",
            "labs", "lab", "laboratory", "library", "printing", "printers",
            "wifi", "wi fi", "internet", "air conditioning", "aircon",
            "canteen", "food", "vending machine", "maintenance", "campus safety",
        ],
        "Administration": [
            "administration", "admin", "administrative", "timetable",
            "timetabling", "scheduling", "module registration", "registration",
            "enrolment", "enrollment", "student portal", "portal",
            "booking system", "bookings", "communication", "announcements",
            "bureaucracy", "student services", "fees",
        ],
        "Well-being": [
            "well being", "wellbeing", "wellness", "mental health",
            "stress", "burnout", "student welfare", "welfare",
            "health", "counselling", "counseling", "mental wellbeing",
            "emotional wellbeing", "work life balance",
        ],
        "Social Environment": [
            "social environment", "social", "campus culture", "culture",
            "harassment", "bullying", "discrimination", "peer relationships",
            "group dynamics", "teamwork", "classmates", "safety",
            "personal safety", "stalking", "inclusion", "diversity",
        ],
        # its own theme since Part 2 (D7); Part 1 counted it under Well-being
        "Workload": [
            "workload", "work load", "heavy workload", "course load",
            "deadlines", "deadline",
        ],
        "Internship Placement": [
            "internship placement", "internship", "internships", "placement",
            "placements", "iwsp", "work study", "work integrated learning",
            "industry attachment", "attachment", "industry placement",
        ],
    }

    # Labels that mean "no real theme"; they become UNCLEAR_THEME.
    __UNCLEAR_WORDS = (
        "unclear", "unknown", "other", "others", "n a", "none", "general",
        "miscellaneous", "misc", "off topic", "no feedback", "spam",
    )

    def __init__(self, known_themes=THEMES):
        self.__alias_lookup = self.__build_alias_lookup()
        self.__unclear_keys = {self.__key(word) for word in self.__UNCLEAR_WORDS}
        self.__known = {}
        self.set_known_themes(known_themes)

    @property
    def known_themes(self) -> tuple[str, ...]:
        """The 8 base themes plus the confirmed new themes, spelled as stored."""
        return tuple(self.__known.values())

    def set_known_themes(self, themes) -> None:
        """Replaces the confirmed themes, e.g. with data.load_known_themes().
        The 8 base themes are always known; blank or unclear labels never are."""
        self.__known = {}
        for theme in (*THEMES, *themes):
            key = self.__key(theme)
            if key and key not in self.__unclear_keys:
                self.__known.setdefault(key, theme)

    def normalise(self, label: str) -> str:
        """Returns, in this order: the base theme the label is an alias of,
        "Unclear" for a blank or unclear label, the confirmed theme it matches,
        or else the label as a new theme, cleaned and in title case."""
        key = self.__key(label)
        if key in self.__alias_lookup:
            return self.__alias_lookup[key]
        if not key or key in self.__unclear_keys:
            return UNCLEAR_THEME
        if key in self.__known:
            return self.__known[key]
        # built from the key, so labels that differ only in case or punctuation get the same name
        return " ".join(word.capitalize() for word in key.split())

    def is_known(self, theme: str) -> bool:
        """True for a base theme or a confirmed new theme (ignoring case and punctuation)."""
        return self.__key(theme) in self.__known

    def is_new(self, label: str) -> bool:
        """True for a real label that is not known yet, so not an alias or Unclear."""
        theme = self.normalise(label)
        return theme != UNCLEAR_THEME and not self.is_known(theme)

    @staticmethod
    def __key(label: str) -> str:
        """Lowercases, turns punctuation into spaces and collapses repeated
        spaces, so 'Well-being', 'well_being' and '  WELL  being ' all become
        'well being'."""
        cleaned = "".join(ch if ch.isalnum() else " " for ch in label.lower())
        return " ".join(cleaned.split())

    def __build_alias_lookup(self) -> dict[str, str]:
        """Flattens the alias table into {key: base theme}. Raises ValueError if
        the table doesn't cover exactly the 8 base themes, or if an alias is
        listed under two themes (the second would silently win)."""
        if set(self.__ALIASES_BY_THEME) != set(THEMES):
            raise ValueError("the alias table must have one entry per base theme in THEMES")
        lookup = {}
        for theme, aliases in self.__ALIASES_BY_THEME.items():
            for alias in [theme, *aliases]:
                key = self.__key(alias)
                if lookup.get(key, theme) != theme:
                    raise ValueError(f"alias '{alias}' is listed under both '{lookup[key]}' and '{theme}'")
                lookup[key] = theme
        return lookup
