from app.assets.loader import PROJECT_ROOT, load_yaml_asset
from app.models.query import MetricPlan


class MetricRegistry:
    """Metric registry loaded from machine-readable metric assets."""

    def __init__(self):
        metric_asset_path = "knowledge/metrics/metric_assets.yaml"
        if not (PROJECT_ROOT / metric_asset_path).exists():
            metric_asset_path = "knowledge/metrics/core_metrics.yaml"

        metric_asset = load_yaml_asset(metric_asset_path)
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
            formula=metric.get("formula") or metric.get("formula_sql") or "",
        )

    def get_many(self, canonical_names: list[str]) -> list[MetricPlan]:
        return [
            plan
            for canonical in canonical_names
            if (plan := self.get(canonical)) is not None
        ]
