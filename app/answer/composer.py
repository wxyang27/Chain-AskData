from app.knowledge_indexer.service import KnowledgeSearchService
from app.models.query import QueryResponse
from app.query_planner.planner import QueryPlanner
from app.sql_generator.generator import SqlGenerator
from app.sql_validator.validator import SqlValidator


class AnswerComposer:
    """组装自然语言取数响应。"""

    def __init__(self):
        self.planner = QueryPlanner()
        self.generator = SqlGenerator()
        self.validator = SqlValidator()
        self.knowledge_search = KnowledgeSearchService()

    def compose(self, question: str) -> QueryResponse:
        retrieval_context = self.knowledge_search.search_structured(question, top_k=10)
        query_plan = self.planner.plan(question, retrieval_context=retrieval_context)
        sql = self.generator.generate(query_plan)
        validation = self.validator.validate(sql)

        return QueryResponse(
            project="Chain-AskData",
            question_summary=f"你想查询：{question}",
            query_plan=query_plan,
            sql=sql,
            validation=validation,
            caliber_notes=[
                "本版本只生成 SQL 与口径说明，不真实执行查询。",
                "核销发生类问题默认使用 executed_date；支付发生类问题默认使用 pay_date。",
                "核销收入使用 exe_income，核销 GMV 使用 exe_amount。",
                "核销客单价默认分母为核销人次 verify_date_id；支付客单价默认分母为支付日期+用户。",
                "门店展示优先使用 sy_hospital_name，主键使用 tenant_id。",
            ],
            retrieval_trace=retrieval_context.raw_matches,
            retrieval_context=retrieval_context.to_dict(),
        )
