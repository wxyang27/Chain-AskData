import re

from app.business.item_progress import (
    ITEM_INCOME_PROGRESS_TEMPLATE,
    extract_item_name,
    is_item_income_progress_question,
    item_income_progress_sql,
)
from app.models.query import QueryPlan


SQL_TEMPLATES = {
    "miracle_collagen_income_progress_mtd": """WITH actual_income AS (
    SELECT  DATE_FORMAT(CAST(CURRENT_DATE() AS TIMESTAMP), 'yyyy-MM') AS month,
            '奇迹胶原' AS standard_name,
            COALESCE(SUM(exe_income), 0) AS actual_exe_income
    FROM    soyoung_dw.dm_opt_qy_user_execution_record_all_d
    WHERE   dp = DATE_SUB(CURRENT_DATE(), 1)
    AND     is_valid = 1
    AND     standard_name REGEXP '奇迹胶原'
    AND     executed_date BETWEEN DATE_FORMAT(CAST(CURRENT_DATE() AS TIMESTAMP), 'yyyy-MM-01')
                              AND DATE_SUB(CURRENT_DATE(), 1)
),
target_income AS (
    SELECT  month,
            third_level_hierarchy AS standard_name,
            SUM(target_absolute_value) AS target_exe_income
    FROM    soyoung_dw.dim_channel_month_income_target
    WHERE   month = DATE_FORMAT(CAST(CURRENT_DATE() AS TIMESTAMP), 'yyyy-MM')
    AND     first_level_hierarchy = '货'
    AND     second_level_hierarchy = '大单品'
    AND     third_level_hierarchy REGEXP '奇迹胶原'
    AND     fourth_level_hierarchy = '整体'
    AND     target_type = '收入'
    GROUP BY month, third_level_hierarchy
)
SELECT  a.actual_exe_income,
        t.target_exe_income,
        DAY(DATE_SUB(CURRENT_DATE(), 1)) AS elapsed_days,
        DAY(LAST_DAY(CURRENT_DATE())) AS month_days,
        a.actual_exe_income / NULLIF(t.target_exe_income, 0) AS target_completion_rate,
        1.0 * DAY(DATE_SUB(CURRENT_DATE(), 1)) / NULLIF(DAY(LAST_DAY(CURRENT_DATE())), 0) AS time_progress_rate,
        (a.actual_exe_income / NULLIF(t.target_exe_income, 0))
        / NULLIF(1.0 * DAY(DATE_SUB(CURRENT_DATE(), 1)) / NULLIF(DAY(LAST_DAY(CURRENT_DATE())), 0), 0) AS time_progress_achievement_rate
FROM    actual_income a
LEFT JOIN target_income t
       ON  a.month = t.month
       AND a.standard_name = t.standard_name;""",
    "execution_summary_yesterday": """SELECT  SUM(exe_income) AS 核销收入,
        SUM(exe_amount) AS 核销GMV,
        COUNT(DISTINCT verify_date_id) AS 核销人次,
        COUNT(DISTINCT customer_id) AS 核销人数,
        SUM(exe_income) / NULLIF(COUNT(DISTINCT verify_date_id),0) AS 核销客单价
FROM    soyoung_dw.dm_opt_qy_user_execution_record_all_d
WHERE   dp = DATE_SUB(CURRENT_DATE(),1)
AND     is_valid = 1
AND     executed_date = DATE_SUB(CURRENT_DATE(),1);""",
    "store_income_top10_30d": """SELECT  b.sy_hospital_name AS 门店,
        SUM(exe_income) AS 核销收入
FROM    soyoung_dw.dm_opt_qy_user_execution_record_all_d a
LEFT JOIN soyoung_dw.dim_qy_tenant_info_all_d b
ON      a.tenant_id = b.tenant_id
AND     b.dp = DATE_SUB(CURRENT_DATE(),1)
WHERE   a.dp = DATE_SUB(CURRENT_DATE(),1)
AND     a.is_valid = 1
AND     a.executed_date BETWEEN DATE_SUB(CURRENT_DATE(),30) AND DATE_SUB(CURRENT_DATE(),1)
GROUP BY b.sy_hospital_name
ORDER BY 核销收入 DESC
LIMIT 10;""",
    "private_new_customer_income_this_week": """SELECT  SUM(exe_income) AS 私域新客核销收入
FROM    soyoung_dw.dm_opt_qy_user_execution_record_all_d
WHERE   dp = DATE_SUB(CURRENT_DATE(),1)
AND     is_valid = 1
AND     executed_date >= DATE_SUB(CURRENT_DATE(), WEEKDAY(CAST(CURRENT_DATE() AS DATETIME)))
AND     executed_date <= DATE_SUB(CURRENT_DATE(),1)
AND     is_new = 1
AND     cx_first_channel = '私域';""",
    "channel_execution_30d": """SELECT  cx_first_channel AS channel_l1,
        SUM(exe_income) AS 核销收入,
        COUNT(DISTINCT verify_date_id) AS 核销人次,
        SUM(exe_income) / NULLIF(COUNT(DISTINCT verify_date_id),0) AS 核销客单价
FROM    soyoung_dw.dm_opt_qy_user_execution_record_all_d
WHERE   dp = DATE_SUB(CURRENT_DATE(),1)
AND     is_valid = 1
AND     executed_date BETWEEN DATE_SUB(CURRENT_DATE(),30) AND DATE_SUB(CURRENT_DATE(),1)
AND     cx_first_channel IN ('私域','公域','老带新')
GROUP BY cx_first_channel;""",
    "new_old_customer_execution_30d": """SELECT  CASE WHEN is_new = 1 THEN '新客' ELSE '老客' END AS 新老客类型,
        SUM(exe_income) AS 核销收入,
        COUNT(DISTINCT verify_date_id) AS 核销人次,
        SUM(exe_income) / NULLIF(COUNT(DISTINCT verify_date_id),0) AS 核销客单价
FROM    soyoung_dw.dm_opt_qy_user_execution_record_all_d
WHERE   dp = DATE_SUB(CURRENT_DATE(),1)
AND     is_valid = 1
AND     executed_date BETWEEN DATE_SUB(CURRENT_DATE(),30) AND DATE_SUB(CURRENT_DATE(),1)
GROUP BY CASE WHEN is_new = 1 THEN '新客' ELSE '老客' END;""",
    "revenue_category_execution_30d": """SELECT  revenue_category AS product_revenue_category,
        SUM(exe_income) AS 核销收入,
        SUM(exe_income) / NULLIF(SUM(SUM(exe_income)) OVER(),0) AS 核销收入占比
FROM    soyoung_dw.dm_opt_qy_user_execution_record_all_d
WHERE   dp = DATE_SUB(CURRENT_DATE(),1)
AND     is_valid = 1
AND     executed_date BETWEEN DATE_SUB(CURRENT_DATE(),30) AND DATE_SUB(CURRENT_DATE(),1)
AND     revenue_category IN ('大单品','常规品','大师团')
GROUP BY revenue_category;""",
    "standard_item_income_top20_30d": """SELECT  standard_name AS standard_item_name,
        SUM(exe_income) AS 核销收入
FROM    soyoung_dw.dm_opt_qy_user_execution_record_all_d
WHERE   dp = DATE_SUB(CURRENT_DATE(),1)
AND     is_valid = 1
AND     executed_date BETWEEN DATE_SUB(CURRENT_DATE(),30) AND DATE_SUB(CURRENT_DATE(),1)
GROUP BY standard_name
ORDER BY 核销收入 DESC
LIMIT 20;""",
    "baoli_newold_execution_mtd": """SELECT  b.sy_hospital_name AS 门店,
        CASE WHEN a.is_new = 1 THEN '新客' ELSE '老客' END AS 新老客类型,
        SUM(a.exe_income) AS 核销收入,
        COUNT(DISTINCT a.verify_date_id) AS 核销人次
FROM    soyoung_dw.dm_opt_qy_user_execution_record_all_d a
LEFT JOIN soyoung_dw.dim_qy_tenant_info_all_d b
ON      a.tenant_id = b.tenant_id
AND     b.dp = DATE_SUB(CURRENT_DATE(),1)
WHERE   a.dp = DATE_SUB(CURRENT_DATE(),1)
AND     a.is_valid = 1
AND     a.executed_date BETWEEN DATETRUNC(CURRENT_DATE(), 'MONTH') AND DATE_SUB(CURRENT_DATE(),1)
AND     b.city_name LIKE '%北京%'
AND     b.sy_hospital_name LIKE '%保利%'
GROUP BY b.sy_hospital_name, CASE WHEN a.is_new = 1 THEN '新客' ELSE '老客' END;""",
    "baoli_daily_execution_30d": """SELECT  a.executed_date,
        b.sy_hospital_name AS 门店,
        SUM(a.exe_income) AS 核销收入,
        COUNT(DISTINCT a.verify_date_id) AS 核销人次,
        SUM(a.exe_income) / NULLIF(COUNT(DISTINCT a.verify_date_id),0) AS 核销客单价
FROM    soyoung_dw.dm_opt_qy_user_execution_record_all_d a
LEFT JOIN soyoung_dw.dim_qy_tenant_info_all_d b
ON      a.tenant_id = b.tenant_id
AND     b.dp = DATE_SUB(CURRENT_DATE(),1)
WHERE   a.dp = DATE_SUB(CURRENT_DATE(),1)
AND     a.is_valid = 1
AND     a.executed_date BETWEEN DATE_SUB(CURRENT_DATE(),30) AND DATE_SUB(CURRENT_DATE(),1)
AND     b.city_name LIKE '%北京%'
AND     b.sy_hospital_name LIKE '%保利%'
GROUP BY a.executed_date, b.sy_hospital_name
ORDER BY a.executed_date;""",
    "baoli_item_execution_mtd": """SELECT  b.sy_hospital_name AS 门店,
        a.standard_name AS 品项,
        SUM(a.exe_income) AS 核销收入,
        COUNT(DISTINCT a.verify_date_id) AS 核销人次,
        SUM(a.exe_income) / NULLIF(COUNT(DISTINCT a.verify_date_id),0) AS 核销客单价
FROM    soyoung_dw.dm_opt_qy_user_execution_record_all_d a
LEFT JOIN soyoung_dw.dim_qy_tenant_info_all_d b
ON      a.tenant_id = b.tenant_id
AND     b.dp = DATE_SUB(CURRENT_DATE(),1)
WHERE   a.dp = DATE_SUB(CURRENT_DATE(),1)
AND     a.is_valid = 1
AND     a.executed_date BETWEEN DATETRUNC(CURRENT_DATE(), 'MONTH') AND DATE_SUB(CURRENT_DATE(),1)
AND     b.city_name LIKE '%北京%'
AND     b.sy_hospital_name LIKE '%保利%'
AND     a.standard_name REGEXP '新一代热玛吉|热玛吉'
GROUP BY b.sy_hospital_name, a.standard_name;""",
    "standard_item_penetration_90d": """WITH base AS (
    SELECT  customer_id,
            standard_name
    FROM    soyoung_dw.dm_opt_qy_user_execution_record_all_d
    WHERE   dp = DATE_SUB(CURRENT_DATE(),1)
    AND     is_valid = 1
    AND     executed_date BETWEEN DATE_SUB(CURRENT_DATE(),90) AND DATE_SUB(CURRENT_DATE(),1)
),
agg AS (
    SELECT  COUNT(DISTINCT customer_id) AS 总核销人数,
            COUNT(DISTINCT CASE WHEN standard_name REGEXP '奇迹胶原' THEN customer_id END) AS 品项核销人数
    FROM    base
)
SELECT  品项核销人数,
        总核销人数,
        品项核销人数 / NULLIF(总核销人数,0) AS 品项渗透率
FROM    agg;""",
    "zero_income_orders_30d": """SELECT  COUNT(DISTINCT main_order_id) AS 0元单量,
        COUNT(DISTINCT customer_id) AS 0元核销人数
FROM    soyoung_dw.dm_opt_qy_user_execution_record_all_d
WHERE   dp = DATE_SUB(CURRENT_DATE(),1)
AND     is_valid = 1
AND     executed_date BETWEEN DATE_SUB(CURRENT_DATE(),30) AND DATE_SUB(CURRENT_DATE(),1)
AND     exe_income = 0;""",
    "zero_income_summary_mtd": """SELECT  COUNT(DISTINCT verify_date_id) AS 0元核销人次,
        COUNT(DISTINCT customer_id) AS 0元核销人数,
        SUM(exe_income) AS 0元核销收入
FROM    soyoung_dw.dm_opt_qy_user_execution_record_all_d
WHERE   dp = DATE_SUB(CURRENT_DATE(),1)
AND     is_valid = 1
AND     executed_date BETWEEN DATETRUNC(CURRENT_DATE(), 'MONTH') AND DATE_SUB(CURRENT_DATE(),1)
AND     exe_income = 0;""",
    "nonzero_execution_summary_mtd": """SELECT  SUM(exe_income) AS 核销收入,
        COUNT(DISTINCT verify_date_id) AS 核销人次,
        SUM(exe_income) / NULLIF(COUNT(DISTINCT verify_date_id),0) AS 核销客单价
FROM    soyoung_dw.dm_opt_qy_user_execution_record_all_d
WHERE   dp = DATE_SUB(CURRENT_DATE(),1)
AND     is_valid = 1
AND     executed_date BETWEEN DATETRUNC(CURRENT_DATE(), 'MONTH') AND DATE_SUB(CURRENT_DATE(),1)
AND     exe_income > 0;""",
    "nonzero_beijing_store_aov_top10_mtd": """SELECT  b.sy_hospital_name AS 门店,
        SUM(a.exe_income) AS 核销收入,
        COUNT(DISTINCT a.verify_date_id) AS 核销人次,
        SUM(a.exe_income) / NULLIF(COUNT(DISTINCT a.verify_date_id),0) AS 核销客单价
FROM    soyoung_dw.dm_opt_qy_user_execution_record_all_d a
LEFT JOIN soyoung_dw.dim_qy_tenant_info_all_d b
ON      a.tenant_id = b.tenant_id
AND     b.dp = DATE_SUB(CURRENT_DATE(),1)
WHERE   a.dp = DATE_SUB(CURRENT_DATE(),1)
AND     a.is_valid = 1
AND     a.executed_date BETWEEN DATETRUNC(CURRENT_DATE(), 'MONTH') AND DATE_SUB(CURRENT_DATE(),1)
AND     a.exe_income > 0
AND     b.city_name LIKE '%北京%'
GROUP BY b.sy_hospital_name
ORDER BY 核销客单价 DESC
LIMIT 10;""",
    "zero_income_visit_rate_mtd": """SELECT  COUNT(DISTINCT CASE WHEN exe_income = 0 THEN verify_date_id END) AS 0元核销人次,
        COUNT(DISTINCT verify_date_id) AS 总核销人次,
        COUNT(DISTINCT CASE WHEN exe_income = 0 THEN verify_date_id END)
        / NULLIF(COUNT(DISTINCT verify_date_id),0) AS 0元单人次占比
FROM    soyoung_dw.dm_opt_qy_user_execution_record_all_d
WHERE   dp = DATE_SUB(CURRENT_DATE(),1)
AND     is_valid = 1
AND     executed_date BETWEEN DATETRUNC(CURRENT_DATE(), 'MONTH') AND DATE_SUB(CURRENT_DATE(),1);""",
    "zero_income_visit_rate_newold_mtd": """SELECT  CASE WHEN is_new = 1 THEN '新客' ELSE '老客' END AS 新老客类型,
        COUNT(DISTINCT CASE WHEN exe_income = 0 THEN verify_date_id END) AS 0元核销人次,
        COUNT(DISTINCT verify_date_id) AS 总核销人次,
        COUNT(DISTINCT CASE WHEN exe_income = 0 THEN verify_date_id END)
        / NULLIF(COUNT(DISTINCT verify_date_id),0) AS 0元单人次占比
FROM    soyoung_dw.dm_opt_qy_user_execution_record_all_d
WHERE   dp = DATE_SUB(CURRENT_DATE(),1)
AND     is_valid = 1
AND     executed_date BETWEEN DATETRUNC(CURRENT_DATE(), 'MONTH') AND DATE_SUB(CURRENT_DATE(),1)
GROUP BY CASE WHEN is_new = 1 THEN '新客' ELSE '老客' END;""",
    "unverified_amount_store_top10": """SELECT  b.sy_hospital_name AS 门店,
        SUM(left_gmv) AS 待核销金额
FROM    soyoung_dw.dm_opt_qy_order_info_all_d a
LEFT JOIN soyoung_dw.dim_qy_tenant_info_all_d b
ON      a.tenant_id = b.tenant_id
AND     b.dp = DATE_SUB(CURRENT_DATE(),1)
WHERE   a.dp = DATE_SUB(CURRENT_DATE(),1)
AND     a.left_num > 0
GROUP BY b.sy_hospital_name
ORDER BY 待核销金额 DESC
LIMIT 10;""",
    "new_customer_payment_30d": """SELECT  SUM(pay_gmv) AS 支付GMV,
        COUNT(DISTINCT uid) AS 支付人数,
        SUM(pay_gmv) / NULLIF(COUNT(DISTINCT CONCAT(CAST(pay_date AS STRING), '_', CAST(uid AS STRING))),0) AS 支付客单价
FROM    soyoung_dw.dm_opt_qy_order_info_all_d
WHERE   dp = DATE_SUB(CURRENT_DATE(),1)
AND     is_paydate_cash = 0
AND     is_pay_new = 1
AND     pay_date BETWEEN DATE_SUB(CURRENT_DATE(),30) AND DATE_SUB(CURRENT_DATE(),1);""",
    "pay_to_verify_rate_30d": """WITH pay_base AS (
    SELECT  main_order_id,
            uid,
            pay_date,
            pay_gmv
    FROM    soyoung_dw.dm_opt_qy_order_info_all_d
    WHERE   dp = DATE_SUB(CURRENT_DATE(),1)
    AND     is_paydate_cash = 0
    AND     pay_date BETWEEN DATE_SUB(CURRENT_DATE(),59) AND DATE_SUB(CURRENT_DATE(),30)
),
verify_base AS (
    SELECT  main_order_id,
            executed_date,
            exe_income
    FROM    soyoung_dw.dm_opt_qy_user_execution_record_all_d
    WHERE   dp = DATE_SUB(CURRENT_DATE(),1)
    AND     is_valid = 1
    AND     executed_date BETWEEN DATE_SUB(CURRENT_DATE(),59) AND DATE_SUB(CURRENT_DATE(),1)
)
SELECT  COUNT(DISTINCT p.main_order_id) AS 支付订单数,
        COUNT(DISTINCT CASE WHEN v.main_order_id IS NOT NULL THEN p.main_order_id END) AS 30日内核销订单数,
        COUNT(DISTINCT CASE WHEN v.main_order_id IS NOT NULL THEN p.main_order_id END)
        / NULLIF(COUNT(DISTINCT p.main_order_id),0) AS 支付后30日核销率
FROM    pay_base p
LEFT JOIN verify_base v
ON      p.main_order_id = v.main_order_id
AND     v.executed_date BETWEEN p.pay_date AND DATE_ADD(p.pay_date,30);""",
    "upgrade_execution_30d": """SELECT  COUNT(DISTINCT customer_id) AS 升单人数,
        COUNT(DISTINCT verify_date_id) AS 升单核销人次,
        SUM(exe_income) AS 升单核销收入
FROM    soyoung_dw.dm_opt_qy_user_execution_record_all_d
WHERE   dp = DATE_SUB(CURRENT_DATE(),1)
AND     is_valid = 1
AND     executed_date BETWEEN DATE_SUB(CURRENT_DATE(),30) AND DATE_SUB(CURRENT_DATE(),1)
AND     is_up = 1;""",
    "upgrade_beijing_store_income_top10_mtd": """SELECT  b.sy_hospital_name AS 门店,
        SUM(a.exe_income) AS 升单核销收入
FROM    soyoung_dw.dm_opt_qy_user_execution_record_all_d a
LEFT JOIN soyoung_dw.dim_qy_tenant_info_all_d b
ON      a.tenant_id = b.tenant_id
AND     b.dp = DATE_SUB(CURRENT_DATE(),1)
WHERE   a.dp = DATE_SUB(CURRENT_DATE(),1)
AND     a.is_valid = 1
AND     a.is_up = 1
AND     a.executed_date BETWEEN DATETRUNC(CURRENT_DATE(), 'MONTH') AND DATE_SUB(CURRENT_DATE(),1)
AND     b.city_name LIKE '%北京%'
GROUP BY b.sy_hospital_name
ORDER BY 升单核销收入 DESC
LIMIT 10;""",
    "laodaixin_new_customer_income_compare_mtd": """SELECT  SUM(CASE WHEN executed_date BETWEEN DATETRUNC(CURRENT_DATE(), 'MONTH') AND DATE_SUB(CURRENT_DATE(),1) THEN exe_income ELSE 0 END) AS 本月核销收入,
        SUM(CASE WHEN executed_date BETWEEN DATEADD(DATETRUNC(CURRENT_DATE(), 'MONTH'), -1, 'mm') AND DATEADD(DATE_SUB(CURRENT_DATE(),1), -1, 'mm') THEN exe_income ELSE 0 END) AS 上月同期核销收入,
        SUM(CASE WHEN executed_date BETWEEN DATETRUNC(CURRENT_DATE(), 'MONTH') AND DATE_SUB(CURRENT_DATE(),1) THEN exe_income ELSE 0 END)
        - SUM(CASE WHEN executed_date BETWEEN DATEADD(DATETRUNC(CURRENT_DATE(), 'MONTH'), -1, 'mm') AND DATEADD(DATE_SUB(CURRENT_DATE(),1), -1, 'mm') THEN exe_income ELSE 0 END) AS 收入差额,
        (SUM(CASE WHEN executed_date BETWEEN DATETRUNC(CURRENT_DATE(), 'MONTH') AND DATE_SUB(CURRENT_DATE(),1) THEN exe_income ELSE 0 END)
        - SUM(CASE WHEN executed_date BETWEEN DATEADD(DATETRUNC(CURRENT_DATE(), 'MONTH'), -1, 'mm') AND DATEADD(DATE_SUB(CURRENT_DATE(),1), -1, 'mm') THEN exe_income ELSE 0 END))
        / NULLIF(SUM(CASE WHEN executed_date BETWEEN DATEADD(DATETRUNC(CURRENT_DATE(), 'MONTH'), -1, 'mm') AND DATEADD(DATE_SUB(CURRENT_DATE(),1), -1, 'mm') THEN exe_income ELSE 0 END),0) AS 变化率
FROM    soyoung_dw.dm_opt_qy_user_execution_record_all_d
WHERE   dp = DATE_SUB(CURRENT_DATE(),1)
AND     is_valid = 1
AND     is_new = 1
AND     cx_first_channel = '老带新';""",
}


class SqlGenerator:
    """根据 QueryPlan 生成 MaxCompute SQL。"""

    def generate(self, query_plan: QueryPlan) -> str:
        template_id = self._specialized_template_id(query_plan)
        if template_id == ITEM_INCOME_PROGRESS_TEMPLATE:
            return item_income_progress_sql(extract_item_name(query_plan.original_question))
        sql = SQL_TEMPLATES.get(
            template_id,
            SQL_TEMPLATES["store_income_top10_30d"],
        )
        sql = self._apply_time_overrides(sql, query_plan)
        return self._apply_question_overrides(sql, query_plan)

    def _specialized_template_id(self, query_plan: QueryPlan) -> str:
        question = query_plan.original_question
        if is_item_income_progress_question(question):
            return ITEM_INCOME_PROGRESS_TEMPLATE
        if "北京" in question and "保利" in question and "新一代热玛吉" in question:
            return "baoli_item_execution_mtd"
        if "北京" in question and "保利" in question and "新客" in question and "老客" in question:
            return "baoli_newold_execution_mtd"
        if "北京" in question and "保利" in question and "按天" in question:
            return "baoli_daily_execution_30d"
        if "老带新" in question and "新客" in question and ("6月同期" in question or "较6月" in question):
            return "laodaixin_new_customer_income_compare_mtd"
        if "0元" in question or "0 元" in question:
            if "剔除" in question and "北京" in question and "门店" in question and "客单价" in question:
                return "nonzero_beijing_store_aov_top10_mtd"
            if "剔除" in question:
                return "nonzero_execution_summary_mtd"
            if "新客" in question and "老客" in question and "占比" in question:
                return "zero_income_visit_rate_newold_mtd"
            if "占核销人次" in question or "人次占比" in question:
                return "zero_income_visit_rate_mtd"
            if "核销人次" in question and "核销人数" in question and "核销收入" in question:
                return "zero_income_summary_mtd"
        if "升单" in question and "北京" in question and "门店" in question and "TOP" in question:
            return "upgrade_beijing_store_income_top10_mtd"
        return query_plan.template_id

    def _apply_time_overrides(self, sql: str, query_plan: QueryPlan) -> str:
        if self._is_this_week(query_plan):
            replacements = {
                "executed_date BETWEEN DATE_SUB(CURRENT_DATE(),30) AND DATE_SUB(CURRENT_DATE(),1)": (
                    "executed_date >= DATE_SUB(CURRENT_DATE(), WEEKDAY(CAST(CURRENT_DATE() AS DATETIME))) "
                    "AND executed_date <= DATE_SUB(CURRENT_DATE(),1)"
                ),
                "pay_date BETWEEN DATE_SUB(CURRENT_DATE(),30) AND DATE_SUB(CURRENT_DATE(),1)": (
                    "pay_date >= DATE_SUB(CURRENT_DATE(), WEEKDAY(CAST(CURRENT_DATE() AS DATETIME))) "
                    "AND pay_date <= DATE_SUB(CURRENT_DATE(),1)"
                ),
            }
            for old, new in replacements.items():
                sql = sql.replace(old, new)
            return sql

        if not self._is_this_month_mtd(query_plan):
            return sql

        replacements = {
            "executed_date BETWEEN DATE_SUB(CURRENT_DATE(),30) AND DATE_SUB(CURRENT_DATE(),1)": (
                "executed_date BETWEEN DATETRUNC(CURRENT_DATE(), 'MONTH') AND DATE_SUB(CURRENT_DATE(),1)"
            ),
            "executed_date BETWEEN DATE_SUB(CURRENT_DATE(),90) AND DATE_SUB(CURRENT_DATE(),1)": (
                "executed_date BETWEEN DATETRUNC(CURRENT_DATE(), 'MONTH') AND DATE_SUB(CURRENT_DATE(),1)"
            ),
            "pay_date BETWEEN DATE_SUB(CURRENT_DATE(),30) AND DATE_SUB(CURRENT_DATE(),1)": (
                "pay_date BETWEEN DATETRUNC(CURRENT_DATE(), 'MONTH') AND DATE_SUB(CURRENT_DATE(),1)"
            ),
            "pay_date BETWEEN DATE_SUB(CURRENT_DATE(),59) AND DATE_SUB(CURRENT_DATE(),30)": (
                "pay_date BETWEEN DATETRUNC(CURRENT_DATE(), 'MONTH') AND DATE_SUB(CURRENT_DATE(),1)"
            ),
        }
        for old, new in replacements.items():
            sql = sql.replace(old, new)
        return sql

    def _apply_question_overrides(self, sql: str, query_plan: QueryPlan) -> str:
        question = query_plan.original_question
        sql = self._apply_city_filter(sql, question)
        sql = self._apply_item_filter(sql, question)
        sql = self._apply_channel_filter(sql, question)
        sql = self._apply_top_n(sql, question)
        return sql

    def _apply_city_filter(self, sql: str, question: str) -> str:
        city = self._named_city(question)
        if not city:
            return sql
        if "city_name LIKE" in sql:
            return re.sub(
                r"city_name LIKE '%[^']+%'",
                f"city_name LIKE '%{city}%'",
                sql,
                count=1,
            )
        if "dim_qy_tenant_info_all_d" not in sql or "GROUP BY" not in sql:
            return sql
        alias = "b." if " b\nON" in sql or " b\r\nON" in sql else ""
        return sql.replace(
            "GROUP BY",
            f"AND     {alias}city_name LIKE '%{city}%'\nGROUP BY",
            1,
        )

    def _apply_item_filter(self, sql: str, question: str) -> str:
        item = self._named_item(question)
        if not item:
            return sql
        if "standard_name REGEXP" in sql:
            return re.sub(
                r"standard_name REGEXP '[^']+'",
                f"standard_name REGEXP '{item}'",
                sql,
                count=1,
            )
        if "GROUP BY" not in sql:
            return sql
        if (
            "standard_name" not in sql
            and "dm_opt_qy_user_execution_record_all_d" not in sql
        ):
            return sql
        alias = "a." if "FROM    soyoung_dw.dm_opt_qy_user_execution_record_all_d a" in sql else ""
        return sql.replace(
            "GROUP BY",
            f"AND     {alias}standard_name REGEXP '{item}'\nGROUP BY",
            1,
        )

    def _apply_channel_filter(self, sql: str, question: str) -> str:
        channel = self._named_channel(question)
        if not channel:
            return sql
        if "cx_first_channel = '" in sql:
            return re.sub(
                r"cx_first_channel = '[^']+'",
                f"cx_first_channel = '{channel}'",
                sql,
                count=1,
            )
        if "cx_first_channel IN" in sql:
            return re.sub(
                r"cx_first_channel IN \([^)]+\)",
                f"cx_first_channel = '{channel}'",
                sql,
                count=1,
            )
        if "GROUP BY" not in sql:
            return sql
        alias = "a." if "FROM    soyoung_dw.dm_opt_qy_user_execution_record_all_d a" in sql else ""
        return sql.replace(
            "GROUP BY",
            f"AND     {alias}cx_first_channel = '{channel}'\nGROUP BY",
            1,
        )

    def _apply_top_n(self, sql: str, question: str) -> str:
        top_n = self._top_n(question)
        if top_n is None:
            return sql
        if re.search(r"\bLIMIT\s+\d+", sql, flags=re.IGNORECASE):
            return re.sub(
                r"\bLIMIT\s+\d+",
                f"LIMIT {top_n}",
                sql,
                count=1,
                flags=re.IGNORECASE,
            )
        if "ORDER BY" in sql:
            return sql.rstrip().rstrip(";") + f"\nLIMIT {top_n};"
        return sql

    def _named_city(self, question: str) -> str:
        for city in (
            "北京", "上海", "广州", "深圳", "武汉", "杭州", "成都", "重庆",
            "天津", "南京", "苏州", "西安", "郑州", "长沙", "青岛", "宁波",
            "合肥", "佛山", "东莞",
        ):
            if city in question:
                return city
        return ""

    def _named_item(self, question: str) -> str:
        for item in ("奇迹胶原", "奇迹童颜", "BBL HERO", "新一代热玛吉", "热玛吉"):
            if item.upper() in question.upper():
                return item
        return ""

    def _named_channel(self, question: str) -> str:
        for channel in ("私域", "公域", "老带新"):
            if channel in question and not all(
                term in question for term in ("私域", "公域", "老带新")
            ):
                return channel
        return ""

    def _top_n(self, question: str) -> int | None:
        match = re.search(r"(?i)top\s*(\d+)", question)
        if match:
            return int(match.group(1))
        match = re.search(r"前\s*(\d+)", question)
        if match:
            return int(match.group(1))
        return None

    def _is_this_month_mtd(self, query_plan: QueryPlan) -> bool:
        if "本月MTD" in query_plan.time_range:
            return True
        return any(
            step.query_semantics.time_type == "this_month_mtd"
            for step in query_plan.query_plan_cot
        )

    def _is_this_week(self, query_plan: QueryPlan) -> bool:
        if "本周" in query_plan.time_range:
            return True
        semantic_contract = getattr(query_plan, "semantic_contract", None)
        if semantic_contract and semantic_contract.time_range == "this_week":
            return True
        return any(
            step.query_semantics.time_type == "this_week"
            for step in query_plan.query_plan_cot
        )
