from app.assets.loader import load_yaml_asset


class SchemaRetriever:
    """Schema 检索入口。

    MVP 先读取本地表资产；后续可在这里替换为 ChromaDB 相似度检索。
    """

    def __init__(self):
        table_asset = load_yaml_asset("knowledge/tables/core_tables.yaml")
        self.tables = {
            table["full_name"]: table
            for table in table_asset["tables"]
        }

    def retrieve(self, source_tables: list[str]) -> list[str]:
        return [
            table_name
            for table_name in source_tables
            if table_name in self.tables
        ]

    def allowed_table_names(self) -> set[str]:
        return {
            table["name"]
            for table in self.tables.values()
        }
