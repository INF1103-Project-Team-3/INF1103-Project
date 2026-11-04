"""Serializable: what the Data Manager needs to save an object as JSON and rebuild it."""

from abc import ABC, abstractmethod
from typing import Self


class Serializable(ABC):
    """Interface: convert to a JSON-ready dictionary and back."""

    @abstractmethod
    def to_dict(self) -> dict:
        """Returns the object as a dictionary that json.dump can write."""

    @classmethod
    @abstractmethod
    def from_dict(cls, data: dict) -> Self:
        """Rebuilds the object from a dictionary made by to_dict().

        Data returns plain dictionaries, so the caller rebuilds the object
        with e.g. AggregationResult.from_dict(data.load_object(...)).
        """
