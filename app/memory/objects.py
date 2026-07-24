"""Short-term conversation memory objects.

The first version stores a small sliding window of structured states.
It is enough for follow-up questions such as "那上海呢" without bringing
summary compression into the main Text2SQL pipeline.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConversationState:
    session_id: str
    turn_id: int = 0
    last_question: str = ""
    last_resolved_question: str = ""
    time_range: str = ""
    metrics: list[str] = field(default_factory=list)
    dimensions: list[str] = field(default_factory=list)
    filters: list[str] = field(default_factory=list)
    top_n: int | None = None
    template_id: str = ""
    last_sql: str = ""

    def has_context(self) -> bool:
        return bool(self.last_resolved_question or self.last_question)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "last_question": self.last_question,
            "last_resolved_question": self.last_resolved_question,
            "time_range": self.time_range,
            "metrics": self.metrics,
            "dimensions": self.dimensions,
            "filters": self.filters,
            "top_n": self.top_n,
            "template_id": self.template_id,
            "last_sql": self.last_sql,
        }


@dataclass
class FollowUpDelta:
    """Structured patch parsed from a follow-up question.

    It describes how the follow-up changes the previous query state.  The
    first iteration uses it to produce a cleaner resolved question; later
    iterations can pass it deeper into semantic planning.
    """

    operations: list[str] = field(default_factory=list)
    set_filters: dict[str, str] = field(default_factory=dict)
    remove_filters: list[str] = field(default_factory=list)
    remove_dimensions: list[str] = field(default_factory=list)
    add_dimensions: list[str] = field(default_factory=list)
    set_metrics: list[str] = field(default_factory=list)
    set_time_range: str = ""
    set_top_n: int | None = None
    output_grain: str = ""
    preserve: list[str] = field(default_factory=list)

    def has_changes(self) -> bool:
        return bool(
            self.operations
            or self.set_filters
            or self.remove_filters
            or self.remove_dimensions
            or self.add_dimensions
            or self.set_metrics
            or self.set_time_range
            or self.set_top_n is not None
            or self.output_grain
            or self.preserve
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "operations": self.operations,
            "set_filters": self.set_filters,
            "remove_filters": self.remove_filters,
            "remove_dimensions": self.remove_dimensions,
            "add_dimensions": self.add_dimensions,
            "set_metrics": self.set_metrics,
            "set_time_range": self.set_time_range,
            "set_top_n": self.set_top_n,
            "output_grain": self.output_grain,
            "preserve": self.preserve,
        }


@dataclass
class MemoryResolution:
    original_question: str
    resolved_question: str
    session_id: str = ""
    used_memory: bool = False
    is_follow_up: bool = False
    reason: str = ""
    previous_state: ConversationState | None = None
    memory_window_size: int = 0
    selected_turn_id: int | None = None
    delta: FollowUpDelta | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "original_question": self.original_question,
            "resolved_question": self.resolved_question,
            "used_memory": self.used_memory,
            "is_follow_up": self.is_follow_up,
            "reason": self.reason,
            "memory_window_size": self.memory_window_size,
            "selected_turn_id": self.selected_turn_id,
            "previous_state": (
                self.previous_state.to_dict()
                if self.previous_state
                else {}
            ),
            "delta": self.delta.to_dict() if self.delta else {},
        }
