"""In-memory short-term conversation store."""

from app.memory.objects import ConversationState


class InMemoryConversationStore:
    """Process-local sliding-window memory store keyed by session_id."""

    def __init__(self, max_turns: int = 3):
        self.max_turns = max_turns
        self._states: dict[str, list[ConversationState]] = {}

    def get(self, session_id: str) -> ConversationState | None:
        """Return the latest state for backward compatibility."""
        if not session_id:
            return None
        window = self._states.get(session_id, [])
        return window[-1] if window else None

    def get_window(self, session_id: str) -> list[ConversationState]:
        if not session_id:
            return []
        return list(self._states.get(session_id, []))

    def save(self, state: ConversationState) -> None:
        if not state.session_id:
            return
        window = self._states.get(state.session_id, [])
        if state.turn_id <= 0:
            last_turn_id = window[-1].turn_id if window else 0
            state.turn_id = last_turn_id + 1
        window.append(state)
        self._states[state.session_id] = window[-self.max_turns:]

    def clear(self, session_id: str) -> None:
        if session_id:
            self._states.pop(session_id, None)


_DEFAULT_STORE = InMemoryConversationStore()


def get_default_memory_store() -> InMemoryConversationStore:
    return _DEFAULT_STORE
