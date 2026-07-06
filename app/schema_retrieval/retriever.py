class SchemaRetriever:
    """Schema 检索接口占位。首版返回固定核心表。"""

    def retrieve_for_store_income(self) -> list[str]:
        return [
            "soyoung_dw.dm_opt_qy_user_execution_record_all_d",
            "soyoung_dw.dim_qy_tenant_info_all_d",
        ]
