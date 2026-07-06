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

    def compose(self, question: str) -> QueryResponse:
        query_plan = self.planner.plan(question)
        sql = self.generator.generate(query_plan)
        validation = self.validator.validate(sql)

        return QueryResponse(
            project="Chain-AskData",
            question_summary=f"你想查询：{question}",
            query_plan=query_plan,
            sql=sql,
            validation=validation,
            caliber_notes=[
                "核销收入使用 SUM(exe_income)。",
                "核销发生量使用 executed_date 作为业务日期。",
                "门店展示优先使用 sy_hospital_name，主键使用 tenant_id。",
            ],
        )
