# StubAI: stands in for AIManager in pipeline tests, with no API calls.

from managers.ai_manager import AISummary


# Agrees with the student on every record, or, when down, classifies nothing and stops.
class StubAI:
    def __init__(self, down=False):
        self.down = down
        self.themes = None
        self.summaries = 0

    def classify_entries(self, records, stored_records, on_classified):
        if self.down:
            return [], list(records), True
        for record in records:
            user = record.user
            record.set_ai(user["theme"], user["sentiment"], user["severity"], "one-liner")
            on_classified(record)
        return list(records), [], False

    def summarise(self, result, records):
        self.summaries += 1
        return AISummary("All fine.", [{"theme": "Facilities", "suggested_action": "Keep going"}])

    def set_known_themes(self, themes):
        self.themes = list(themes)
