"""Rule-based follow-up detection and question completion."""

from __future__ import annotations

import re

from app.memory.objects import ConversationState, FollowUpDelta, MemoryResolution


ITEM_NAMES = ("奇迹胶原", "奇迹童颜", "BBL HERO", "新一代热玛吉", "热玛吉")
CITY_NAMES = (
    "北京", "上海", "广州", "深圳", "武汉", "杭州", "成都", "重庆",
    "天津", "南京", "苏州", "西安", "郑州", "长沙", "青岛", "宁波",
    "合肥", "佛山", "东莞",
)
CHANNEL_NAMES = ("私域", "公域", "老带新")
AREA_NAMES = ("华北", "华东", "华南", "华中")
STORE_NAME_HINTS = ("保利",)
PAYMENT_METRIC_ALIASES = (
    "支付GMV", "支付 GMV", "支付收入", "支付金额", "支付额",
    "收款金额", "收款", "流水", "付款金额", "付款额", "付了多少",
)
EXECUTION_INCOME_ALIASES = ("核销收入", "核销金额", "消耗收入", "消耗金额")
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
        delta = self._parse_delta(original)
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
        if not self.is_follow_up(original, delta):
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
        resolved = self._rewrite_from_delta(base, delta)
        if not resolved:
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
            delta=delta if delta.has_changes() else None,
        )

    def is_follow_up(
        self,
        question: str,
        delta: FollowUpDelta | None = None,
    ) -> bool:
        q = question.strip()
        normalized = self._normalize(q)
        if delta and delta.has_changes():
            return True
        if any(q.startswith(prefix) for prefix in FOLLOW_UP_PREFIXES):
            return True
        if any(phrase in q for phrase in ("回到", "回看", "还是", "刚才", "那个")):
            return True
        if self._extract_top_n(q) is not None and len(normalized) <= 8:
            return True
        if len(normalized) <= 10 and (
            self._find_item(q) or self._find_city(q) or self._find_channel(q)
            or self._find_area(q)
            or self._find_store(q)
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
        store = self._find_store(clean)
        if city and store:
            result = self._replace_or_append_location(result, city, store)
        elif city:
            result = self._replace_or_append(result, CITY_NAMES, city)

        area = self._find_area(clean)
        if area:
            result = self._replace_or_append_area(result, area)

        channel = self._find_channel(clean)
        if channel:
            result = self._replace_or_append(result, CHANNEL_NAMES, channel)

        if store and not city:
            result = self._replace_or_append_store(result, store)

        time_phrase = self._find_time_phrase(clean)
        if time_phrase:
            result = self._replace_time(result, time_phrase)

        top_n = self._extract_top_n(clean)
        if top_n is not None:
            result = self._replace_top_n(result, top_n)

        return result

    def _parse_delta(self, question: str) -> FollowUpDelta:
        q = question.strip()
        clean = self._clean_follow_up(q)
        compact_follow_up = (
            len(self._normalize(clean)) <= 12
            or any(q.startswith(prefix) for prefix in FOLLOW_UP_PREFIXES)
            or any(term in q for term in ("换成", "改成", "改看", "那", "呢"))
        )
        delta = FollowUpDelta()

        channel = self._find_channel(clean)
        if channel and any(term in q for term in ("只看", "单看", "仅看")):
            delta.operations.append("channel_narrowing")
            delta.set_filters["cx_first_channel"] = channel
            delta.preserve.extend(["time_range", "metrics"])

        if any(term in q for term in ("不要门店", "不用门店", "不看门店", "去掉门店")) and "整体" in q:
            delta.operations.append("dimension_removal")
            delta.remove_dimensions.append("sy_hospital_name")
            delta.output_grain = "overall"
            delta.preserve.extend(["time_range", "metrics", "filters"])

        if "收入占比" in q:
            delta.operations.append("metric_switch_to_ratio")
            delta.set_metrics.append("execution_income_share")
            delta.preserve.extend(["time_range", "dimensions", "top_n", "filters"])

        time_phrase = self._find_time_phrase(clean)
        if time_phrase and (clean == time_phrase or compact_follow_up):
            delta.set_time_range = time_phrase
            delta.preserve.extend(["metrics", "filters", "dimensions", "top_n"])

        if any(alias in q for alias in PAYMENT_METRIC_ALIASES) and compact_follow_up:
            delta.operations.append("domain_switch_to_payment")
            delta.set_metrics.append("payment_gmv")
            delta.preserve.extend(["time_range", "city", "item", "dimensions", "top_n"])

        if any(alias in q for alias in EXECUTION_INCOME_ALIASES) and any(
            term in q for term in ("换成", "改成", "改看")
        ):
            delta.operations.append("domain_switch_to_execution")
            delta.set_metrics.append("execution_income")
            delta.preserve.extend(["time_range", "city", "item", "dimensions", "top_n"])

        return delta

    def _rewrite_from_delta(self, base: str, delta: FollowUpDelta) -> str:
        if not delta.has_changes():
            return ""
        operations = set(delta.operations)

        if "channel_narrowing" in operations:
            channel = delta.set_filters.get("cx_first_channel", "")
            if channel:
                return self._channel_narrowing_question(base, channel)

        if "dimension_removal" in operations and delta.output_grain == "overall":
            return self._overall_question(base)

        if "metric_switch_to_ratio" in operations:
            return self._income_share_question(base)

        if "domain_switch_to_payment" in operations:
            return self._payment_gmv_question(base, delta.set_time_range)

        if "domain_switch_to_execution" in operations:
            result = self._execution_income_question(base)
            if delta.set_time_range:
                result = self._replace_time(result, delta.set_time_range)
            return result

        return ""

    def _channel_narrowing_question(self, base: str, channel: str) -> str:
        time_phrase = self._time_from_base(base)
        if "核销收入" in base and "人次" in base and "客单价" in base:
            return f"{time_phrase}{channel}核销收入、人次、客单价"
        return self._replace_channel_set(base, channel)

    def _overall_question(self, base: str) -> str:
        time_phrase = self._time_from_base(base)
        if "核销收入" in base:
            return f"{time_phrase}整体核销收入是多少？"
        if "支付GMV" in base:
            return f"{time_phrase}整体支付GMV是多少？"
        return f"{time_phrase}整体数据是多少？"

    def _income_share_question(self, base: str) -> str:
        result = base
        if "核销收入占比" not in result:
            result = result.replace("核销收入", "核销收入占比", 1)
        return result

    def _payment_gmv_question(self, base: str, time_phrase: str = "") -> str:
        result = base
        if "核销收入" in result:
            result = result.replace("核销收入", "支付GMV", 1)
        elif "支付GMV" not in result:
            result = f"{result}，支付GMV"
        if time_phrase:
            result = self._replace_time(result, time_phrase)
        return result

    def _execution_income_question(self, base: str) -> str:
        result = base
        for alias in PAYMENT_METRIC_ALIASES:
            if alias in result:
                return result.replace(alias, "核销收入", 1)
        if "核销收入" not in result:
            result = f"{result}，核销收入"
        return result

    def _replace_channel_set(self, base: str, channel: str) -> str:
        result = base
        patterns = (
            "私域、公域、老带新",
            "私域/公域/老带新",
            "私域、公域和老带新",
        )
        for pattern in patterns:
            if pattern in result:
                result = result.replace(pattern, channel, 1)
                break
        return result.replace("对比", "").strip("，, ")

    def _time_from_base(self, base: str) -> str:
        for phrase in TIME_PHRASES:
            if phrase in base:
                return phrase
        match = re.search(r"最近\d+天|近\d+天", base)
        if match:
            return match.group(0)
        return ""

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
            for term in (*CITY_NAMES, *AREA_NAMES, *ITEM_NAMES, *CHANNEL_NAMES)
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

    def _replace_or_append_store(self, base: str, store: str) -> str:
        if store in base:
            return base
        if base.endswith("是多少？"):
            return base.replace("是多少？", f"，{store}店是多少？", 1)
        return f"{base}，{store}店"

    def _replace_or_append_location(self, base: str, city: str, store: str) -> str:
        location = f"{city}{store}店"
        if city in base and store in base:
            return base
        if store in base:
            return self._replace_or_append(base, CITY_NAMES, city)
        if base.endswith("是多少？"):
            return base.replace("是多少？", f"，{location}是多少？", 1)
        return f"{base}，{location}"

    def _replace_or_append_area(self, base: str, area: str) -> str:
        for candidate in AREA_NAMES:
            if candidate in base and candidate != area:
                return base.replace(candidate, area)
        if area in base:
            return base
        if base.endswith("是多少？"):
            return base.replace("是多少？", f"，{area}大区是多少？", 1)
        return f"{base}，{area}大区"

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

    def _find_area(self, question: str) -> str:
        for area in AREA_NAMES:
            if area in question:
                return area
        return ""

    def _find_store(self, question: str) -> str:
        if any(term in question for term in ("各门店", "各店", "门店TOP", "门店排行")):
            return ""
        for store in STORE_NAME_HINTS:
            if store in question:
                return store
        cleaned = question
        for city in CITY_NAMES:
            cleaned = cleaned.replace(city, "")
        cleaned = re.sub(r"(想看|看一下|看下|只看|单看|那|那个|如果是|换成|改成|呢|的)", "", cleaned)
        match = re.search(r"([\u4e00-\u9fa5A-Za-z0-9 ]{2,20})店", cleaned)
        if not match:
            return ""
        store = match.group(1).strip()
        return store if store and store not in {"门", "门店"} else ""

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
