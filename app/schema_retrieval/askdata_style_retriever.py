from pathlib import Path
from typing import Any

from app.knowledge_indexer.retrieval_context import RetrievalContext
from app.schema_graph.builder import SchemaGraphBuilder
from app.schema_index.loader import SchemaIndexBundle, SchemaIndexLoader


class AskDataStyleSchemaRetriever:
    """AskData-style SchemaGraph retrieval over local generated indexes."""

    def __init__(
        self,
        schema_indexes: SchemaIndexBundle | None = None,
        indexes_dir: Path | str = Path("knowledge/generated/indexes"),
    ):
        self.schema_indexes = schema_indexes or SchemaIndexLoader().load(indexes_dir)
        self.schema_graph_builder = SchemaGraphBuilder(schema_indexes=self.schema_indexes)

    def retrieve(self, retrieval_context: RetrievalContext) -> dict[str, Any]:
        schema_graph = self.schema_graph_builder.build(retrieval_context)
        return {
            "retriever": "askdata_style_schema_retriever",
            "schema_graph": schema_graph,
            "schema_graph_text": schema_graph.schema_graph_text,
            "field_count": len(schema_graph.fields),
            "table_count": len(schema_graph.tables),
            "metric_count": len(schema_graph.metrics),
            "relation_count": len(schema_graph.relations),
        }
