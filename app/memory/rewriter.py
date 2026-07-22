"""Rule-based follow-up detection and question completion."""

from __future__ import annotations

import re

from app.memory.objects import ConversationState, MemoryResolution


ITEM_NAMES = ("奇迹胶原", "奇迹童颜", "BBL HERO", "新一代热玛吉", "热玛吉")
CITY_NAMES = (
    "北京", "上海", "广州", "深圳", "武汉", "杭州", "成都", "重庆",
    "天津", "南京", "苏州", "西安", "郑州", "长沙", "青岛", "宁波",
    "合肥", "佛山", "东莞",
)
CHANNEL_NAMES = ("私域", "公域", "老带新")
TIME_PHRASES = (
    "本月", "这个月", "当月", "本周", "这周", "昨天", "截至昨天",
    "最近7天", "近7天", "最近30天", "近30天", "最近60天", "近60天",
    "最近90天", "近90天",
)
FOLLOW_UP_PREFIXES = (
    "那", "那么", "换成", "改成", "再看", "再", "继续", "同样",
    "回到", "回看", "还是", "刚才",
)


class QuestionRewriter:
    """Complete a short follow-up question using the latest state."""

    def resolve(
        self,
        question: str,
        state: ConversationState | list[ConversationState] | None,
        *,
        session_id: str = "",
        enabled: bool = True,
    ) -> MemoryResolution:
        original = question.strip()
        states = self._as_state_window(state)
        if not enabled or not session_id:
            return MemoryResolution(
                original_question=original,
                resolved_question=original,
                session_id=session_id,
                reason="memory_disabled",
            )
        if not states:
            return MemoryResolution(
                original_question=original,
                resolved_question=original,
                session_id=session_id,
                reason="no_previous_state",
            )
        if not self.is_follow_up(original):
            return MemoryResolution(
                original_question=original,
                resolved_question=original,
                session_id=session_id,
                previous_state=states[-1],
                memory_window_size=len(states),
                selected_turn_id=states[-1].turn_id,
                reason="standalone_question",
            )

        selected_state = self._select_base_state(original, states)
        base = selected_state.last_resolved_question or selected_state.last_question
        resolved = self._rewrite_from_base(base, original)
        if resolved == base:
            resolved = f"{base}，{self._clean_follow_up(original)}"

        return MemoryResolution(
            original_question=original,
            resolved_question=resolved,
            session_id=session_id,
            used_memory=True,
            is_follow_up=True,
            reason="follow_up_rewritten",
            previous_state=selected_state,
            memory_window_size=len(states),
            selected_turn_id=selected_state.turn_id,
        )

    def is_follow_up(self, question: str) -> bool:
        q = question.strip()
        normalized = self._normalize(q)
        if any(q.startswith(prefix) for prefix in FOLLOW_UP_PREFIXES):
            return True
        if any(phrase in q for phrase in ("回到", "回看", "还是", "刚才", "那个")):
            return True
        if self._extract_top_n(q) is not None and len(normalized) <= 8:
            return True
        if len(normalized) <= 10 and (
            self._find_item(q) or self._find_city(q) or self._find_channel(q)
            or self._find_time_phrase(q)
        ):
            return True
        return False

    def _rewrite_from_base(self, base: str, follow_up: str) -> str:
        result = base
        clean = self._clean_follow_up(follow_up)

        item = self._find_item(clean)
        if item:
            result = self._replace_or_append(result, ITEM_NAMES, item)

        city = self._find_city(clean)
        if city:
            result = self._replace_or_append(result, CITY_NAMES, city)

        channel = self._find_channel(clean)
        if channel:
            result = self._replace_or_append(result, CHANNEL_NAMES, channel)

        time_phrase = self._find_time_phrase(clean)
        if time_phrase:
            result = self._replace_time(result, time_phrase)

        top_n = self._extract_top_n(clean)
        if top_n is not None:
            result = self._replace_top_n(result, top_n)

        return result

    def _as_state_window(
        self,
        state: ConversationState | list[ConversationState] | None,
    ) -> list[ConversationState]:
        if state is None:
            return []
        if isinstance(state, ConversationState):
            return [state] if state.has_context() else []
        return [s for s in state if s.has_context()]

    def _select_base_state(
        self,
        question: str,
        states: list[ConversationState],
    ) -> ConversationState:
        if self._references_first_turn(question):
            return states[0]

        explicit_match = self._match_explicit_reference(question, states)
        if explicit_match:
            return explicit_match

        return states[-1]

    def _references_first_turn(self, question: str) -> bool:
        return any(
            phrase in question
            for phrase in ("刚才第一个", "第一个", "最开始", "一开始", "第一轮")
        )

    def _match_explicit_reference(
        self,
        question: str,
        states: list[ConversationState],
    ) -> ConversationState | None:
        has_reference_signal = any(
            phrase in question
            for phrase in ("回到", "回看", "还是", "刚才", "那个")
        )
        if not has_reference_signal:
            return None

        mentioned_terms = [
            term
            for term in (*CITY_NAMES, *ITEM_NAMES, *CHANNEL_NAMES)
            if term.upper() in question.upper()
        ]
        if not mentioned_terms:
            return states[0] if "回到" in question else None

        for state in reversed(states):
            base = state.last_resolved_question or state.last_question
            if any(term.upper() in base.upper() for term in mentioned_terms):
                return state
        return None

    def _replace_or_append(
        self,
        base: str,
        candidates: tuple[str, ...],
        replacement: str,
    ) -> str:
        for candidate in candidates:
            if candidate in base and candidate != replacement:
                return base.replace(candidate, replacement)
        if replacement in base:
            return base
        return f"{base}，{replacement}"

    def _replace_time(self, base: str, replacement: str) -> str:
        patterns = [
            r"最近\d+天",
            r"近\d+天",
            r"截至昨天",
            r"本月",
            r"这个月",
            r"当月",
            r"本周",
            r"这周",
            r"昨天",
        ]
        for pattern in patterns:
            if re.search(pattern, base):
                return re.sub(pattern, replacement, base, count=1)
        return f"{replacement}{base}"

    def _replace_top_n(self, base: str, top_n: int) -> str:
        if re.search(r"(?i)top\s*\d+", base):
            return re.sub(r"(?i)top\s*\d+", f"TOP{top_n}", base, count=1)
        if re.search(r"前\s*\d+", base):
            return re.sub(r"前\s*\d+", f"前{top_n}", base, count=1)
        return f"{base} TOP{top_n}"

    def _clean_follow_up(self, question: str) -> str:
        q = question.strip().strip("？?。 ")
        for prefix in FOLLOW_UP_PREFIXES:
            if q.startswith(prefix):
                q = q[len(prefix):].strip()
                break
        return q.strip()

    def _find_item(self, question: str) -> str:
        upper_q = question.upper()
        for item in ITEM_NAMES:
            if item.upper() in upper_q:
                return item
        return ""

    def _find_city(self, question: str) -> str:
        for city in CITY_NAMES:
            if city in question:
                return city
        return ""

    def _find_channel(self, question: str) -> str:
        for channel in CHANNEL_NAMES:
            if channel in question:
                return channel
        return ""

    def _find_time_phrase(self, question: str) -> str:
        for phrase in TIME_PHRASES:
            if phrase in question:
                return phrase
        return ""

    def _extract_top_n(self, question: str) -> int | None:
        match = re.search(r"(?i)top\s*(\d+)", question)
        if match:
            return int(match.group(1))
        match = re.search(r"前\s*(\d+)", question)
        if match:
            return int(match.group(1))
        return None

    def _normalize(self, text: str) -> str:
        return "".join(text.split()).strip("？?。,.，")
