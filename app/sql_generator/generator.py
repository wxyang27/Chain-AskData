from app.models.query import QueryPlan


class SqlGenerator:
    """根据 QueryPlan 生成 MaxCompute SQL。"""

    def generate(self, query_plan: QueryPlan) -> str:
        return """SELECT  b.sy_hospital_name AS 门店,
        SUM(a.exe_income) AS 核销收入
FROM    soyoung_dw.dm_opt_qy_user_execution_record_all_d a
JOIN    soyoung_dw.dim_qy_tenant_info_all_d b
ON      a.tenant_id = b.tenant_id
AND     b.dp = DATE_SUB(CURRENT_DATE(),1)
WHERE   a.dp = DATE_SUB(CURRENT_DATE(),1)
AND     a.is_valid = 1
AND     a.executed_date BETWEEN DATE_SUB(CURRENT_DATE(),30) AND DATE_SUB(CURRENT_DATE(),1)
GROUP BY b.sy_hospital_name
ORDER BY 核销收入 DESC
LIMIT 10;"""
