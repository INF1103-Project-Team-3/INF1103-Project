
import logging
from datetime import datetime
from pathlib import Path
from typing import Final

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ("feedback_id", "text", "timestamp")
SUPPORTED_EXTENSIONS = (".csv", ".json")
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S"
MAX_REPROMPTS: Final = 3
QUIT_COMMANDS = ("q", "quit")
MAX_TEXT_LENGTH = 2000