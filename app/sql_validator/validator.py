import re

from app.models.query import ValidationResult


class SqlValidator:
    """SQL 安全与口径校验器。"""

    WRITE_PATTERN = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE)\b", re.I)

    def validate(self, sql: str) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        normalized = sql.strip()
        upper_sql = normalized.upper()

        if not (upper_sql.startswith("SELECT") or upper_sql.startswith("WITH")):
            errors.append("只允许生成 SELECT 或 WITH 查询")

        if self.WRITE_PATTERN.search(upper_sql):
            errors.append("只允许生成 SELECT 或 WITH 查询")

        if "SOYOUNG_DW." in upper_sql and not re.search(r"\bdp\s*=", sql, re.I):
            errors.append("SQL 必须包含 dp 分区条件，避免全表扫描")

        if "ORDER BY" in upper_sql and "LIMIT" not in upper_sql:
            errors.append("出现 ORDER BY 时必须包含 LIMIT")

        if "DM_OPT_QY_USER_EXECUTION_RECORD_ALL_D" in upper_sql and "IS_VALID" not in upper_sql:
            errors.append("核销主表必须包含 is_valid = 1")

        if "DM_OPT_QY_ORDER_INFO_ALL_D" in upper_sql and "LEFT_NUM" not in upper_sql and "IS_PAYDATE_CASH" not in upper_sql:
            errors.append("支付主表发生量必须包含 is_paydate_cash = 0")

        return ValidationResult(
            passed=not errors,
            errors=errors,
            warnings=warnings,
        )
