from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from managers.ai_manager import AISummary
    from managers.io_manager import SessionResult
    from managers.logic_manager import (
        ActionSuggestions,
        AggregationResult,
        ImpactReport,
        TrendReport,
    )
    from managers.models import FeedbackRecord


@dataclass
class PipelineContext:
    data_dir: str = "data"
    session: SessionResult | None = None
    records: list[FeedbackRecord] = field(default_factory=list)
    invalid_records: list[tuple[FeedbackRecord, list[str]]] = field(default_factory=list)
    review_queue: list[FeedbackRecord] = field(default_factory=list)
    result: AggregationResult | None = None
    trend: TrendReport | None = None
    summary: AISummary | None = None
    impacts: list[ImpactReport] = field(default_factory=list)
    fallback_actions: ActionSuggestions | None = None
    classified_count: int = 0
    stopped: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
