import unittest

from app.sql_validator.validator import SqlValidator


class SqlValidatorTestCase(unittest.TestCase):
    def setUp(self):
        self.validator = SqlValidator()

    def test_rejects_write_sql(self):
        result = self.validator.validate("DELETE FROM soyoung_dw.test_table")

        self.assertFalse(result.passed)
        self.assertIn("只允许生成 SELECT 或 WITH 查询", result.errors)

    def test_requires_dp_partition_for_whitelisted_table(self):
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


if __name__ == "__main__":
    unittest.main()
