import subprocess
import sys

import pytest

import managers.data_manager as data_package
from managers.data_manager import DataManager


def test_store_is_not_public(tmp_path):
    assert not hasattr(DataManager(str(tmp_path)), "json_store")


def test_data_dir_is_read_only(tmp_path):
    data = DataManager(str(tmp_path))
    assert data.data_dir == tmp_path
    with pytest.raises(AttributeError):
        data.data_dir = tmp_path / "other"


def test_no_module_level_helper_is_exported():
    assert not hasattr(data_package, "_read_list_strict")
    assert "_read_list_strict" not in data_package.__all__


def test_importing_data_manager_leaves_logging_unconfigured():
    """Logging is set up once by the app (AppEngine), not as a side effect of an import."""
    code = ("import logging, managers.data_manager; "
            "print(len(logging.getLogger().handlers))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "0"
