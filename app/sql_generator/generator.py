from app.models.query import QueryPlan


SQL_TEMPLATES = {
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
        SUM(a.exe_income) AS 核销收入
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
        SUM(exe_income) AS 核销收入
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
        SUM(pay_gmv) / NULLIF(COUNT(DISTINCT CASE WHEN pay_flag = 1 THEN CONCAT(CAST(pay_date AS STRING), '_', CAST(uid AS STRING)) END),0) AS 支付客单价
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
}


class SqlGenerator:
    """根据 QueryPlan 生成 MaxCompute SQL。"""

    def generate(self, query_plan: QueryPlan) -> str:
        sql = SQL_TEMPLATES.get(
            query_plan.template_id,
            SQL_TEMPLATES["store_income_top10_30d"],
        )
        return self._apply_time_overrides(sql, query_plan)

    def _apply_time_overrides(self, sql: str, query_plan: QueryPlan) -> str:
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

    def _is_this_month_mtd(self, query_plan: QueryPlan) -> bool:
        if "本月MTD" in query_plan.time_range:
            return True
        return any(
            step.query_semantics.time_type == "this_month_mtd"
            for step in query_plan.query_plan_cot
        )
