from fastapi import APIRouter

from app.answer.composer import AnswerComposer
from app.models.query import QueryRequest, QueryResponse

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """健康检查接口。"""

    return {
        "project": "Chain-AskData",
        "status": "ok",
    }


@router.post("/query", response_model=QueryResponse)
def query(request: QueryRequest) -> QueryResponse:
    """自然语言取数接口，首版只生成 SQL 和口径说明。"""

    composer = AnswerComposer()
    return composer.compose(request.question)
