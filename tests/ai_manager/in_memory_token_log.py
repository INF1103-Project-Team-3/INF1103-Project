"""InMemoryTokenLog: stands in for the Data Manager's token log, with no files."""

import json


class InMemoryTokenLog:
    """load and save go in the places of data.load_token_log and data.save_token_log."""

    def __init__(self):
        self.log = {}
        self.corrupt = False  # load returns None, as Data does for a corrupt log
        self.saves = 0

    def load(self) -> dict | None:
        return None if self.corrupt else json.loads(json.dumps(self.log))

    def save(self, log: dict) -> None:
        self.log = json.loads(json.dumps(log))
        self.saves += 1
