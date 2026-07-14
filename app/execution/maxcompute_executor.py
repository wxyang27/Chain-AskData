"""MaxCompute executor skeleton.

The project currently keeps real warehouse execution disabled by default.  This
class is intentionally a stub so the pipeline boundary is clear without forcing
PyODPS credentials or network access during demos/tests.
"""

from app.execution.base import SqlExecutor
from app.execution.objects import SqlExecutionRequest, SqlExecutionResult


class MaxComputeSqlExecutor(SqlExecutor):
    @property
    def mode(self) -> str:
        return "maxcompute"

    @property
    def enabled(self) -> bool:
        return True

    def execute(self, request: SqlExecutionRequest) -> SqlExecutionResult:
        return SqlExecutionResult(
            enabled=True,
            mode=self.mode,
            status="failed",
            sql=request.sql,
            error=(
                "maxcompute_not_configured: this demo only exposes the execution "
                "boundary; configure PyODPS credentials before enabling real reads"
            ),
            dry_run=True,
        )
