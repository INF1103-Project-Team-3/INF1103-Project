"""PasswordValidator: checks the admin password without exposing it."""
import pytest

from managers.io_manager.password_validator import PasswordValidator


def test_correct_password_is_accepted():
    assert PasswordValidator("s3cret").check("s3cret") == (True, "")


def test_wrong_password_is_rejected():
    assert PasswordValidator("s3cret").check("S3CRET") == (None, "wrong password")


@pytest.mark.parametrize("missing", [None, ""])
def test_admin_login_is_disabled_without_a_password(missing):
    validator = PasswordValidator(missing)
    assert validator.is_configured is False
    # even an empty answer must not match an empty password
    assert validator.check("") == (None, "wrong password")


def test_password_cannot_be_read_from_outside():
    validator = PasswordValidator("s3cret")
    with pytest.raises(AttributeError):
        validator.__password            # private: name-mangled by Python
    assert "s3cret" not in repr(validator)
