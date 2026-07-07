import unittest

from app.sql_validator.validator import SqlValidator


class SqlValidatorTestCase(unittest.TestCase):
    """SQL 口径与安全校验。"""

    def setUp(self):
        self.validator = SqlValidator()

    def test_rejects_write_sql(self):
        result = self.validator.validate("DELETE FROM soyoung_dw.test_table")

        self.assertFalse(result.passed)
        self.assertIn("只允许生成 SELECT 或 WITH 查询", result.errors)

    def test_requires_dp_partition_for_soyoung_dw_table(self):
        sql = "SELECT SUM(exe_income) FROM soyoung_dw.dm_opt_qy_user_execution_record_all_d"

        result = self.validator.validate(sql)

        self.assertFalse(result.passed)
        self.assertIn("SQL 必须包含 dp 分区条件，避免全表扫描", result.errors)

    def test_requires_limit_when_order_by_exists(self):
        sql = """
        SELECT sy_hospital_name, SUM(exe_income) AS 核销收入
        FROM soyoung_dw.dm_opt_qy_user_execution_record_all_d
        WHERE dp = DATE_SUB(CURRENT_DATE(),1)
        AND is_valid = 1
        ORDER BY 核销收入 DESC
        """

        result = self.validator.validate(sql)

        self.assertFalse(result.passed)
        self.assertIn("出现 ORDER BY 时必须包含 LIMIT", result.errors)

    def test_rejects_execution_sql_without_is_valid(self):
        sql = """
        SELECT SUM(exe_income) AS 核销收入
        FROM soyoung_dw.dm_opt_qy_user_execution_record_all_d
        WHERE dp = DATE_SUB(CURRENT_DATE(),1)
        AND executed_date = DATE_SUB(CURRENT_DATE(),1)
        """

        result = self.validator.validate(sql)

        self.assertFalse(result.passed)
        self.assertIn("核销事实表必须过滤 is_valid = 1", result.errors)

    def test_rejects_execution_sql_without_executed_date(self):
        sql = """
        SELECT SUM(exe_income) AS 核销收入
        FROM soyoung_dw.dm_opt_qy_user_execution_record_all_d
        WHERE dp = DATE_SUB(CURRENT_DATE(),1)
        AND is_valid = 1
        """

        result = self.validator.validate(sql)

        self.assertFalse(result.passed)
        self.assertIn("核销发生类问题必须使用 executed_date 作为业务日期", result.errors)

    def test_rejects_execution_distinct_uid_as_user_count(self):
        sql = """
        SELECT COUNT(DISTINCT uid) AS 核销人数
        FROM soyoung_dw.dm_opt_qy_user_execution_record_all_d
        WHERE dp = DATE_SUB(CURRENT_DATE(),1)
        AND is_valid = 1
        AND executed_date = DATE_SUB(CURRENT_DATE(),1)
        """

        result = self.validator.validate(sql)

        self.assertFalse(result.passed)
        self.assertIn("核销人数必须按 customer_id 去重，不能直接用 uid", result.errors)

    def test_rejects_exe_amount_as_income(self):
        sql = """
        SELECT SUM(exe_amount) AS 核销收入
        FROM soyoung_dw.dm_opt_qy_user_execution_record_all_d
        WHERE dp = DATE_SUB(CURRENT_DATE(),1)
        AND is_valid = 1
        AND executed_date = DATE_SUB(CURRENT_DATE(),1)
        """

        result = self.validator.validate(sql)

        self.assertFalse(result.passed)
        self.assertIn("核销收入必须使用 exe_income，exe_amount 是核销 GMV", result.errors)

    def test_rejects_penetration_with_product_name(self):
        sql = """
        SELECT COUNT(DISTINCT CASE WHEN product_name REGEXP '奇迹胶原' THEN customer_id END) AS 品项核销人数
        FROM soyoung_dw.dm_opt_qy_user_execution_record_all_d
        WHERE dp = DATE_SUB(CURRENT_DATE(),1)
        AND is_valid = 1
        AND executed_date BETWEEN DATE_SUB(CURRENT_DATE(),90) AND DATE_SUB(CURRENT_DATE(),1)
        """

        result = self.validator.validate(sql)

        self.assertFalse(result.passed)
        self.assertIn("品项经营口径优先使用 standard_name，不能用 product_name 替代", result.errors)

    def test_requires_payment_cash_filter_except_unverified_inventory(self):
        sql = """
        SELECT SUM(pay_gmv) AS 支付GMV
        FROM soyoung_dw.dm_opt_qy_order_info_all_d
        WHERE dp = DATE_SUB(CURRENT_DATE(),1)
        AND pay_date BETWEEN DATE_SUB(CURRENT_DATE(),30) AND DATE_SUB(CURRENT_DATE(),1)
        """

        result = self.validator.validate(sql)

        self.assertFalse(result.passed)
        self.assertIn("支付发生类问题必须过滤 is_paydate_cash = 0，剔除当日退款", result.errors)

    def test_rejects_unverified_inventory_with_pay_date_window(self):
        sql = """
        SELECT SUM(left_gmv) AS 待核销金额
        FROM soyoung_dw.dm_opt_qy_order_info_all_d
        WHERE dp = DATE_SUB(CURRENT_DATE(),1)
        AND left_num > 0
        AND pay_date BETWEEN DATE_SUB(CURRENT_DATE(),30) AND DATE_SUB(CURRENT_DATE(),1)
        """

        result = self.validator.validate(sql)

        self.assertFalse(result.passed)
        self.assertIn("待核销是库存快照口径，默认不应按 pay_date 发生期截断", result.errors)

    def test_rejects_unknown_soyoung_dw_table(self):
        sql = """
        SELECT COUNT(1)
        FROM soyoung_dw.some_unknown_table
        WHERE dp = DATE_SUB(CURRENT_DATE(),1)
        """

        result = self.validator.validate(sql)

        self.assertFalse(result.passed)
        self.assertIn("发现未登记的 soyoung_dw 表：some_unknown_table", result.errors)

    def test_rejects_sensitive_fields(self):
        sql = """
        SELECT mobile, real_name
        FROM soyoung_dw.dim_user_qy_crm_customer_info_all_d
        WHERE dp = DATE_SUB(CURRENT_DATE(),1)
        """

        result = self.validator.validate(sql)

        self.assertFalse(result.passed)
        self.assertIn("MVP 默认不允许输出敏感字段：mobile", result.errors)
        self.assertIn("MVP 默认不允许输出敏感字段：real_name", result.errors)


if __name__ == "__main__":
    unittest.main()
