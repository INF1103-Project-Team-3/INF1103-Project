from __future__ import annotations

import hmac

from .input_validator import InputValidator


class PasswordValidator(InputValidator):
    """Checks the admin password.

    Encapsulation: the password is stored in a private attribute (double
    underscore), so no other class can read it, only ask check(). The password
    is passed in from outside (it comes from the environment); I never put it
    in the source code. If none is supplied, admin login is switched off and
    check() always fails.
    """

    def __init__(self, password: str | None):
        self.__password = password or ""

    @property
    def is_configured(self) -> bool:
        """False when no password was supplied, so admin login is disabled."""
        return bool(self.__password)

    def check(self, answer: str):
        # compare_digest takes the same time however many characters match,
        # so the comparison cannot leak information about the password
        if self.is_configured and hmac.compare_digest(
                answer.encode("utf-8"), self.__password.encode("utf-8")):
            return True, ""
        return None, "wrong password"
