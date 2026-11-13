# Fills managers/live_data with six dated runs of made-up feedback, so the Trends page has history.
# Run with the GUI closed: python -m demo.seed_live_data   (a backup of the folder is made first)

import random
import shutil
import sys
from datetime import date, datetime, time, timedelta

from managers.data_manager import DataManager
from managers.io_manager import EntryValidator, RecordBuilder, ReviewDecision, SessionResult, ThemeValidator
from managers.logic_manager import LogicManager
from managers.models import SEVERITIES

from .gui_live import DATA_DIR
from .seed_entries import ENTRIES, FACILITIES_AFTER, FACILITIES_BEFORE, PARKING
from .interim_pipeline import InterimPipeline

RUN_DAYS_AGO = (25, 20, 15, 10, 5, 0)
WIFI_FIX_DAYS_AGO = 13
CONFIRM_RUN = 4

# New entries per run (runs 2 to 6) for each theme. The entries themselves are in seed_entries.
PLAN = {
    "Facilities": (6, 7, 3, 1, 1),
    "Assessment": (1, 2, 4, 6, 7),
    "Workload": (2, 3, 4, 4, 3),
    "Well-being": (2, 2, 3, 3, 4),
    "Teaching Quality": (2, 2, 2, 2, 2),
    "Administration": (1, 1, 0, 2, 1),
    "Social Environment": (0, 1, 1, 1, 2),
    PARKING: (0, 0, 2, 3, 3),
}


# Stands in for the AI without API calls: mostly agrees with the student, sometimes not.
class SeedAI:
    def __init__(self, rng: random.Random):
        self.__rng = rng

    def classify_entries(self, records, stored_records, on_classified):
        for record in records:
            theme, sentiment, severity = (record.user[f] for f in ("theme", "sentiment", "severity"))
            roll = self.__rng.random()
            if roll < 0.08:
                theme = self.__rng.choice([t for t in PLAN if t not in (theme, PARKING)])
            elif roll < 0.2:
                step = SEVERITIES.index(severity) + self.__rng.choice((-1, 1))
                severity = SEVERITIES[min(max(step, 0), len(SEVERITIES) - 2)]
            summary = " ".join(record.text.split()[:12])
            record.set_ai(theme, sentiment, severity, summary)
            on_classified(record)
        return list(records), [], False

    # Returns None so the real AI summary already saved is kept.
    def summarise(self, result, records):
        return None

    def set_known_themes(self, themes):
        pass


# Each theme's entries in a shuffled order; every entry is handed out once.
def entry_pools(rng: random.Random) -> dict[str, list]:
    pools = {theme: list(entries) for theme, entries in ENTRIES.items()}
    pools["Facilities before"] = list(FACILITIES_BEFORE)
    pools["Facilities after"] = list(FACILITIES_AFTER)
    for pool in pools.values():
        rng.shuffle(pool)
    return pools


# One run's new records, timestamped between the previous run and this one.
def build_batch(run: int, start: datetime, end: datetime, rng: random.Random,
                validator: EntryValidator, counter: list[int], pools: dict[str, list]) -> list:
    records = []
    seconds = int((end - start).total_seconds())
    fixed_on = date.today() - timedelta(days=WIFI_FIX_DAYS_AGO)
    for theme, counts in PLAN.items():
        for _ in range(counts[run - 1]):
            counter[0] += 1
            stamp = start + timedelta(seconds=rng.randrange(seconds))
            pool = theme
            if theme == "Facilities":
                pool = "Facilities after" if stamp.date() >= fixed_on else "Facilities before"
            text, sentiment, severity = pools[pool].pop()
            raw = {"feedback_id": f"seed_{counter[0]:03d}", "text": text,
                   "timestamp": stamp.strftime("%Y-%m-%dT%H:%M:%S"), "theme": theme,
                   "sentiment": sentiment, "severity": severity}
            entry, error = validator.validate(raw, require_ids=True)
            if error:
                raise ValueError(f"seed entry {raw['feedback_id']}: {error}")
            records.append(RecordBuilder().build(entry, source_file=f"seed-run-{run + 1}"))
    return records


def main() -> int:
    data = DataManager(str(DATA_DIR))
    if any(entry["feedback_id"].startswith("seed_") for entry in data.load_records()):
        print("managers/live_data is already seeded. Delete the folder (or restore a backup) first.")
        return 1
    backup = DATA_DIR.with_name(f"live_data_backup_{datetime.now():%Y%m%d-%H%M%S}")
    shutil.copytree(DATA_DIR, backup)
    print(f"Backed up to {backup}")

    rng = random.Random(1103)
    logic = LogicManager()
    logic.set_known_themes(data.load_known_themes())
    validator = EntryValidator(ThemeValidator(logic))
    data.json_store.save(data.data_dir / "aggregated_history.json", [])

    today = date.today()
    run_dates = [today - timedelta(days=days) for days in RUN_DAYS_AGO]
    counter, first_parking = [0], None
    pools = entry_pools(rng)
    for index, run_date in enumerate(run_dates):
        moment = datetime.combine(run_date, time(17, 0))
        session = SessionResult(source_file="stress-input.json" if index == 0 else f"seed-run-{index + 1}")
        if index > 0:
            start = datetime.combine(run_dates[index - 1], time(17, 0))
            session.records = build_batch(index, start, moment, rng, validator, counter, pools)
            parking = [r for r in session.records if r.user["theme"] == PARKING]
            first_parking = first_parking or (parking[0] if parking else None)
        if index == 3:
            session.actions.append(RecordBuilder(clock=lambda: moment).build_action(
                "Facilities", "Upgraded the library Wi-Fi access points",
                (today - timedelta(days=WIFI_FIX_DAYS_AGO)).isoformat(), "wifi"))
        if index == CONFIRM_RUN and first_parking is not None:
            session.decisions.append(ReviewDecision.update(first_parking.feedback_id, first_parking.user))
        if index == 5:
            session.actions.append(RecordBuilder(clock=lambda: moment).build_action(
                "Assessment", "Published marking rubrics for every assignment",
                (today - timedelta(days=4)).isoformat()))
        pipeline = InterimPipeline(data, logic, SeedAI(rng), today=lambda d=run_date: d,
                                   clock=lambda m=moment: m)
        context = pipeline.execute_pipeline(session)
        print(f"Run {index + 1} ({run_date}): {len(session.records)} new, "
              f"{context.result.counted_entries} counted of {context.result.total_entries}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
