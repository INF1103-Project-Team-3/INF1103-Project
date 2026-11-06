import pytest

from managers.models import Serializable


class _Point(Serializable):
    def __init__(self, x):
        self.x = x

    def to_dict(self):
        return {"x": self.x}

    @classmethod
    def from_dict(cls, data):
        return cls(data["x"])


class _NoFromDict(Serializable):
    def to_dict(self):
        return {}


def test_interface_cannot_be_created():
    with pytest.raises(TypeError):
        Serializable()


def test_class_missing_from_dict_cannot_be_created():
    with pytest.raises(TypeError):
        _NoFromDict()


def test_round_trip_rebuilds_an_equal_object():
    assert _Point.from_dict(_Point(3).to_dict()).x == 3
