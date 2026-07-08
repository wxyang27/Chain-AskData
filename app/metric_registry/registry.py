from app.assets.loader import load_yaml_asset
from app.models.query import MetricPlan


class MetricRegistry:
    """MVP 指标注册表，从机器可读资产加载标准口径。"""

    def __init__(self):
        metric_asset = load_yaml_asset("knowledge/metrics/core_metrics.yaml")
        self.metrics = {
            metric["canonical"]: metric
            for metric in metric_asset["metrics"]
        }

    def get(self, canonical: str) -> MetricPlan | None:
        metric = self.metrics.get(canonical)
        if metric is None:
            return None
        return MetricPlan(
            canonical=metric["canonical"],
            display_name=metric["display_name"],
            formula=metric["formula"],
        )

    def get_many(self, canonical_names: list[str]) -> list[MetricPlan]:
        return [
            plan
            for canonical in canonical_names
            if (plan := self.get(canonical)) is not None
        ]
