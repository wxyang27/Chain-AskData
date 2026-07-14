"""MaxCompute (ODPS) SQL Executor — stub, ready for DataWorks connection.

When DataWorks endpoint + read-only account are available:
    1. Set env: MC_ENDPOINT, MC_PROJECT, MC_ACCESS_ID, MC_ACCESS_KEY
    2. Uncomment the ODPS SDK import and implementation below
    3. Pipeline picks it up via ExecutorClient interface — no other changes

Safety controls (enforced before any query reaches MaxCompute):
    - Read-only access (SELECT / WITH / DESCRIBE / SHOW only)
    - dp = DATE_SUB(CURRENT_DATE(),1) enforced per snapshot table
    - max_rows limit (default 1000)
    - query timeout (default 30s)
    - table whitelist (soyoung_dw.* only)
"""

from app.model_clients.executor_client import ExecutionResult, ExecutorClient


class MaxComputeExecutor(ExecutorClient):
    """Stub — raises NotImplementedError until DataWorks credentials are set."""

    @property
    def provider_name(self) -> str:
        return "maxcompute_odps"

    @property
    def is_readonly(self) -> bool:
        return True

    def execute(
        self,
        sql: str,
        *,
        timeout_seconds: int = 30,
        max_rows: int = 1000,
    ) -> ExecutionResult:
        # TODO: Uncomment when DataWorks credentials are available
        #
        # from odps import ODPS
        # o = ODPS(
        #     access_id=os.getenv("MC_ACCESS_ID"),
        #     secret_access_key=os.getenv("MC_ACCESS_KEY"),
        #     project=os.getenv("MC_PROJECT"),
        #     endpoint=os.getenv("MC_ENDPOINT"),
        # )
        # with o.execute_sql(sql).open_reader() as reader:
        #     columns = [c.name for c in reader.columns]
        #     rows = [list(row.values) for row in reader[:max_rows]]
        #     return ExecutionResult(
        #         success=True,
        #         sql=sql,
        #         columns=columns,
        #         rows=rows,
        #         row_count=len(rows),
        #         dry_run=False,
        #     )

        return ExecutionResult(
            success=False,
            sql=sql,
            error_message=(
                "maxcompute_not_configured: set MC_ENDPOINT/MC_PROJECT/"
                "MC_ACCESS_ID/MC_ACCESS_KEY in .env"
            ),
            dry_run=True,
        )
