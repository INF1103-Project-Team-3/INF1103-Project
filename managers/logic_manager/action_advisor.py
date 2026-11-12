"""ActionAdvisor: suggested actions from keyword rules, for when the AI's summary can't run."""

import re

from managers.models import CRITICAL, NEGATIVE, FeedbackRecord

from .results import ActionSuggestions, AggregationResult


class ActionAdvisor:
    """Picks one action per theme from a fixed table, with no AI (design reference D21).

    For each theme: critical feedback is always sent to the right team first.
    Then the keyword rule that the most negative entries mention wins, matched
    as whole words in the raw text; with no match, the theme's default action.
    A theme with no negative feedback gets "keep doing it", and a theme outside
    the table (a confirmed new theme) gets a general action.
    """

    # theme -> ([(keywords, action), ...], default action). To support a new
    # problem, add a rule to its theme.
    __RULES = {
        "Teaching Quality": ([
            (("pace", "pacing", "fast", "rush", "rushed", "rushing", "speed"),
             "Review lecture pacing with the teaching team and add recaps or recordings for the fastest topics."),
            (("confusing", "unclear", "explain", "explanation", "slides"),
             "Ask lecturers to clarify the topics students find confusing and add worked examples to the slides."),
        ], "Share the teaching feedback with module leads and agree one improvement per module."),
        "Assessment": ([
            (("marking", "marked", "marks", "grade", "grades", "grading", "graded", "rubric", "criteria"),
             "Publish clear marking criteria and check that grading is consistent across markers."),
            (("returned", "delay", "delayed", "late"),
             "Set and publish a turnaround time for returning marked work and feedback."),
            (("group", "groupmate", "groupmates", "contribution"),
             "Add peer review to group assessments so each member's contribution counts."),
            (("syllabus", "excluded", "scope", "brief"),
             "Check that exams and assignment briefs only cover what students were told to prepare."),
            (("copied", "copying", "plagiarism", "cheating"),
             "Remind students how to report academic misconduct and follow up every report."),
        ], "Review the assessment briefs students mention with module leads and explain any changes."),
        "Facilities": ([
            (("wiring", "railing", "loose", "leak", "leaking", "fire", "hazard", "dangerous", "hurt"),
             "Ask estates to inspect and fix the safety hazards students mention as a priority."),
            (("wifi", "wi-fi", "internet", "network"),
             "Check Wi-Fi coverage and reliability in the areas students mention with IT services."),
            (("printer", "printers", "printing"),
             "Ask IT to service the printers and publish how to report a faulty one."),
            (("aircon", "air conditioning", "cold", "hot"),
             "Ask estates to check the temperature control in the rooms students mention."),
            (("lift", "lifts", "broken", "repair", "projector", "computers", "machine", "machines"),
             "Report the broken equipment to estates and tell students when it will be fixed."),
            (("toilet", "toilets", "soap", "dirty", "clean", "cleaning"),
             "Ask estates to increase cleaning and restocking in the areas students mention."),
        ], "Pass the facilities problems to estates and IT, with the locations students mention."),
        "Administration": ([
            (("timetable", "timetabling", "schedule", "clash"),
             "Check the timetable for clashes and publish changes earlier."),
            (("portal", "website", "login", "system"),
             "Ask IT to check the student portal's reliability and announce outages."),
            (("email", "emails", "reply", "response"),
             "Set a response time for student enquiries and send key updates through one channel."),
            (("results", "fees", "grant", "scholarship", "transcript"),
             "Give students a named contact for results, fees and grants, and explain each decision in writing."),
        ], "Simplify the administrative processes students mention, starting with the most common requests."),
        "Well-being": ([
            (("stress", "stressed", "anxiety", "anxious", "overwhelmed", "burnout", "pressure", "cope", "coping",
              "exhausted", "too much"),
             "Promote counselling and well-being support, especially around exams and deadlines."),
            (("lonely", "isolated", "alone"),
             "Organise peer support and social activities for students who feel isolated."),
        ], "Make sure students know how to reach counselling and well-being support."),
        "Social Environment": ([
            (("harass", "harassed", "harassment", "bully", "bullying", "threatening", "unsafe", "touching",
              "following", "stalking", "uncomfortable", "humiliating", "discrimination"),
             "Remind students how to report harassment and make sure every report is followed up."),
            (("group", "groupmates", "teammates"),
             "Give guidance on fair group work and a way to report members who don't contribute."),
        ], "Gather more detail on the social problems raised and involve student welfare."),
        "Workload": ([
            (("deadline", "deadlines", "due", "clashing"),
             "Check the assessment calendar for clashing deadlines and spread them out where possible."),
            (("hours", "heavy", "overload", "overloaded"),
             "Compare each module's workload with its stated study hours and reduce the heaviest."),
        ], "Review workload across modules with module leads and adjust where it is heaviest."),
        "Internship Placement": ([
            (("interview", "interviews", "applications", "offers"),
             "Share more placement openings and run application and interview workshops."),
            (("photocopying", "data entry", "project work", "unrelated"),
             "Check with placement companies that students get work related to their course."),
            (("supervisor", "mentor"),
             "Check in with placement supervisors and give students a clear contact for problems."),
        ], "Review placement support with the careers team and act on the main problems raised."),
    }
    # who handles critical feedback for a theme; anything else goes to student welfare
    __CRITICAL_TEAMS = {
        "Well-being": "student counselling",
        "Social Environment": "student welfare and campus safety",
        "Facilities": "campus safety and estates",
    }
    __DEFAULT_TEAM = "student welfare"

    def suggest(self, result: AggregationResult, records: list[FeedbackRecord]) -> ActionSuggestions:
        """One action per theme in result, in the same order. Expects records
        that have been through the rules; only counted ones are read."""
        actions = []
        for stats in result.themes:
            theme_records = [r for r in records if r.counted and r.theme == stats.theme]
            actions.append({"theme": stats.theme, "suggested_action": self.__action(stats.theme, theme_records)})
        return ActionSuggestions(actions)

    def __action(self, theme: str, records: list[FeedbackRecord]) -> str:
        negative_texts = [r.text for r in records if r.sentiment == NEGATIVE]
        if not negative_texts:
            action = f"Keep doing what students praise about {theme}."
        elif theme in self.__RULES:
            action = self.__best_rule(theme, negative_texts)
        else:
            action = (f"Look into the {len(negative_texts)} negative {self.__plural(len(negative_texts), 'entry', 'entries')} "
                      f"about {theme} and decide who should own it.")

        critical = sum(r.severity == CRITICAL for r in records)
        if critical:
            team = self.__CRITICAL_TEAMS.get(theme, self.__DEFAULT_TEAM)
            return (f"First pass the {critical} critical {self.__plural(critical, 'report', 'reports')} to {team} "
                    f"for immediate follow-up. {action}")
        return action

    def __best_rule(self, theme: str, texts: list[str]) -> str:
        """The action whose keywords the most texts mention; ties go to the earlier rule."""
        rules, default = self.__RULES[theme]
        best, best_count = default, 0
        for keywords, action in rules:
            count = sum(any(self.__mentions(text, word) for word in keywords) for text in texts)
            if count > best_count:
                best, best_count = action, count
        return best

    @staticmethod
    def __mentions(text: str, word: str) -> bool:
        """True when text has word as a whole word, in any case."""
        return re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text, re.IGNORECASE) is not None

    @staticmethod
    def __plural(count: int, one: str, many: str) -> str:
        return one if count == 1 else many
