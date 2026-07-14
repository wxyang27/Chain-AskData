import re

from app.models.query import ValidationResult
from app.schema_retrieval.retriever import SchemaRetriever


class SqlValidator:
    """SQL 安全与业务口径校验器。"""

    WRITE_PATTERN = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE)\b", re.I)
    SOYOUNG_TABLE_PATTERN = re.compile(r"\bsoyoung_dw\.([a-zA-Z0-9_]+)\b", re.I)
    SENSITIVE_FIELDS = {
        "mobile",
        "phone",
        "telephone",
        "real_name",
        "user_name",
        "id_card",
        "identity_card",
    }

    def __init__(self):
        self.allowed_tables = SchemaRetriever().allowed_table_names()

    def validate(self, sql: str) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        normalized = sql.strip()
        upper_sql = normalized.upper()

        self._validate_readonly(normalized, upper_sql, errors)
        self._validate_partition(normalized, upper_sql, errors)
        self._validate_limit(upper_sql, errors)
        self._validate_table_whitelist(normalized, errors)
        self._validate_execution_caliber(normalized, upper_sql, errors)
        self._validate_payment_caliber(normalized, upper_sql, errors)
        self._validate_penetration_caliber(normalized, upper_sql, errors)
        self._validate_sensitive_fields(normalized, errors)

        return ValidationResult(
            passed=not errors,
            errors=errors,
            warnings=warnings,
        )

    def _validate_readonly(self, sql: str, upper_sql: str, errors: list[str]) -> None:
        if not (upper_sql.startswith("SELECT") or upper_sql.startswith("WITH")):
            errors.append("只允许生成 SELECT 或 WITH 查询")
            return

        if self.WRITE_PATTERN.search(sql):
            errors.append("只允许生成 SELECT 或 WITH 查询")

    def _validate_partition(self, sql: str, upper_sql: str, errors: list[str]) -> None:
        if "SOYOUNG_DW." in upper_sql and not re.search(r"\bdp\s*=", sql, re.I):
            errors.append("SQL 必须包含 dp 分区条件，避免全表扫描")

    def _validate_limit(self, upper_sql: str, errors: list[str]) -> None:
        if "ORDER BY" in upper_sql and "LIMIT" not in upper_sql:
            errors.append("出现 ORDER BY 时必须包含 LIMIT")

    def _validate_table_whitelist(self, sql: str, errors: list[str]) -> None:
        found_tables = {
            match.group(1).lower()
            for match in self.SOYOUNG_TABLE_PATTERN.finditer(sql)
        }
        for table_name in sorted(found_tables):
            if table_name not in self.allowed_tables:
                errors.append(f"发现未登记的 soyoung_dw 表：{table_name}")

    def _validate_execution_caliber(self, sql: str, upper_sql: str, errors: list[str]) -> None:
        if "DM_OPT_QY_USER_EXECUTION_RECORD_ALL_D" not in upper_sql:
            return

        if not re.search(r"\bis_valid\s*=\s*1\b", sql, re.I):
            errors.append("核销事实表必须过滤 is_valid = 1")

        if re.search(r"\bSUM\s*\(\s*(?:[a-z]\.)?exe_income\s*\)", sql, re.I):
            if not re.search(r"\bexecuted_date\b", sql, re.I):
                errors.append("核销发生类问题必须使用 executed_date 作为业务日期")

        if re.search(r"COUNT\s*\(\s*DISTINCT\s+(?:[a-z]\.)?uid\s*\)", sql, re.I):
            if "核销" in sql:
                errors.append("核销人数必须按 customer_id 去重，不能直接用 uid")

        if re.search(r"SUM\s*\(\s*(?:[a-z]\.)?exe_amount\s*\)\s+AS\s+核销收入", sql, re.I):
            errors.append("核销收入必须使用 exe_income，exe_amount 是核销 GMV")

    def _validate_payment_caliber(self, sql: str, upper_sql: str, errors: list[str]) -> None:
        if "DM_OPT_QY_ORDER_INFO_ALL_D" not in upper_sql:
            return

        is_unverified_inventory = "LEFT_NUM" in upper_sql and "LEFT_GMV" in upper_sql
        has_payment_metric = any(metric in upper_sql for metric in ["PAY_GMV", "支付GMV", "支付客单价"])

        if has_payment_metric and not re.search(r"\bis_paydate_cash\s*=\s*0\b", sql, re.I):
            errors.append("支付发生类问题必须过滤 is_paydate_cash = 0，剔除当日退款")

        if is_unverified_inventory and re.search(r"\bpay_date\s+BETWEEN\b", sql, re.I):
            errors.append("待核销是库存快照口径，默认不应按 pay_date 发生期截断")

    def _validate_penetration_caliber(self, sql: str, upper_sql: str, errors: list[str]) -> None:
        is_item_business = "品项" in sql or "渗透率" in sql or "REGEXP" in upper_sql
        if is_item_business and "PRODUCT_NAME" in upper_sql:
            errors.append("品项经营口径优先使用 standard_name，不能用 product_name 替代")

    def _validate_sensitive_fields(self, sql: str, errors: list[str]) -> None:
        for field in sorted(self.SENSITIVE_FIELDS):
            if re.search(rf"\b{field}\b", sql, re.I):
                errors.append(f"MVP 默认不允许输出敏感字段：{field}")
