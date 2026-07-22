"""Lightweight MCP-style capability registry.

This is intentionally not a full MCP server.  It gives the planning model a
small, explicit view of the databases and tools that the local pipeline has
registered, so planning stays within executable boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.config import settings


@dataclass(frozen=True)
class DatabaseCapability:
    """A database/project that the pipeline is allowed to plan against."""

    name: str
    engine: str
    readonly: bool = True
    enabled: bool = True
    description: str = ""


@dataclass(frozen=True)
class ToolCapability:
    """A tool-like capability available to the local Agentic workflow."""

    name: str
    description: str
    allowed_databases: list[str] = field(default_factory=list)
    enabled: bool = True


@dataclass(frozen=True)
class CapabilityContext:
    """Promptable capability context inspired by MCP tools/list."""

    databases: list[DatabaseCapability] = field(default_factory=list)
    tools: list[ToolCapability] = field(default_factory=list)

    def allowed_database_names(self) -> set[str]:
        return {database.name for database in self.databases if database.enabled}

    def default_database_name(self) -> str:
        for database in self.databases:
            if database.enabled:
                return database.name
        return settings.odps_project_name or "soyoung_dw"

    def to_prompt_context(self) -> str:
        """Render a concise capability block for the CoT planning prompt."""
        lines = [
            "# Available Databases",
        ]
        for database in self.databases:
            status = "enabled" if database.enabled else "disabled"
            readonly = "readonly" if database.readonly else "readwrite"
            description = f" - {database.description}" if database.description else ""
            lines.append(
                f"- {database.name}: engine={database.engine}, "
                f"access={readonly}, status={status}{description}"
            )

        lines.append("")
        lines.append("# Available Tools")
        for tool in self.tools:
            status = "enabled" if tool.enabled else "disabled"
            databases = ", ".join(tool.allowed_databases) or "none"
            lines.append(
                f"- {tool.name}: status={status}, "
                f"allowed_databases=[{databases}], {tool.description}"
            )

        lines.append("")
        lines.append(
            "Planning rule: choose database only from enabled Available Databases; "
            "do not invent database names, tools, APIs, or direct database connections."
        )
        return "\n".join(lines)


def create_default_capability_context() -> CapabilityContext:
    """Build the current local capability context.

    soyoung_analysis is intentionally not exposed yet.  The registry shape is
    multi-database ready, but only databases present here are visible to the
    model and allowed by the CoT validator.
    """
    database_name = settings.odps_project_name or "soyoung_dw"
    databases = [
        DatabaseCapability(
            name=database_name,
            engine="maxcompute",
            readonly=True,
            enabled=True,
            description="新氧连锁经营数仓默认项目",
        )
    ]
    tools = [
        ToolCapability(
            name="schema_retrieval",
            description="召回已注册的表、字段和表关系，不直接连接数据库",
            allowed_databases=[database_name],
        ),
        ToolCapability(
            name="query_plan_cot",
            description="基于 SchemaGraph 和能力清单生成受控查询计划",
            allowed_databases=[database_name],
        ),
        ToolCapability(
            name="sql_safety_gate",
            description="校验 SQL 只读性、表字段来源、分区和业务口径规则",
            allowed_databases=[database_name],
        ),
        ToolCapability(
            name="sql_execution",
            description=(
                "通过已注册执行器执行只读查询；模型不能直接持有凭证或连接数据库"
            ),
            allowed_databases=[database_name],
            enabled=settings.execution_mode.strip().lower() != "disabled",
        ),
    ]
    return CapabilityContext(databases=databases, tools=tools)
