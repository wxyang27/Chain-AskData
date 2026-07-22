"""SQL execution layer for Chain-AskData.

This package keeps execution behind a small interface so the online pipeline can
switch between disabled, mock, sqlite, and future MaxCompute execution without
changing Text2SQL generation logic.
"""

from app.execution.base import SqlExecutor
from app.execution.capabilities import (
    CapabilityContext,
    DatabaseCapability,
    ToolCapability,
    create_default_capability_context,
)
from app.execution.factory import create_sql_executor
from app.execution.objects import SqlExecutionRequest, SqlExecutionResult

__all__ = [
    "CapabilityContext",
    "DatabaseCapability",
    "SqlExecutionRequest",
    "SqlExecutionResult",
    "SqlExecutor",
    "ToolCapability",
    "create_sql_executor",
    "create_default_capability_context",
]
