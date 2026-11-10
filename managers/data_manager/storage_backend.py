from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

class StorageBackend(ABC):
    """Interface for storage backends."""
    
    @abstractmethod
    def load(self, path: Path) -> Any:
        pass

    @abstractmethod
    def save(self, path: Path, data: Any) -> bool:
        pass