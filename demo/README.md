# GUI demo (temporary)

Runs the PySide6 admin window on the stress-test samples, with no API calls.
`FakeDataManager` and `FakePipeline` stand in for Data and the pipeline until
their refactors are merged; AppEngine replaces this folder.

From the repo root, on your laptop (not Docker, which has no screen):

```bash
pip install -r requirements/requirements.txt -r requirements/gui.txt
python -m demo.gui_demo          # opens the window
python -m pytest tests/gui -v    # GUI tests (offscreen)
```

Demo admin password: `admin`.

What works now:

- Start page: student feedback or admin login
- Student form: submitted entries wait for the next "Process" run
- Dashboard: number cards
- Add feedback: process pending entries with live progress
- Feedback: needs review / all feedback, search, review decisions
- Trends & actions: line chart from sample run history, log action
