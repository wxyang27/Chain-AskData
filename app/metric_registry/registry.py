from app.models.query import MetricPlan


class MetricRegistry:
    """MVP 指标注册表。后续会从 YAML/Markdown 资产加载。"""

    def get_store_income_metric(self) -> MetricPlan:
        return MetricPlan(
            canonical="store_exe_income",
            display_name="门店核销收入",
            formula="SUM(exe_income)",
        )
