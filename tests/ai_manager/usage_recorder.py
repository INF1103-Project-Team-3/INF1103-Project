"""UsageRecorder: records Groq's raw responses during a live run."""

import requests


class UsageRecorder:
    """Records every Groq response's status and token usage by wrapping
    requests.Session.post, so the measurement needs no change to GroqClient."""

    def __init__(self):
        self.responses = []
        self.__post = requests.Session.post

    def install(self) -> None:
        recorder = self

        def post(session, *args, **kwargs):
            response = recorder.__post(session, *args, **kwargs)
            try:
                usage = response.json().get("usage", {})
            except ValueError:
                usage = {}
            recorder.responses.append({"status": response.status_code, "usage": usage, "body": response.text[:300]})
            return response

        requests.Session.post = post
