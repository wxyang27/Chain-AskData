from fastapi import APIRouter, Query

from app.answer.composer import AnswerComposer
from app.knowledge_indexer.service import KnowledgeSearchService
from app.models.query import QueryRequest, QueryResponse
from app.cot_planning.planner import QueryPlanner

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """健康检查接口。"""

    return {
        "project": "Chain-AskData",
        "status": "ok",
    }


@router.get("/demo-queries")
def demo_queries() -> list[dict]:
    """返回 MVP 阶段可演示的自然语言问题。"""

    return QueryPlanner().list_demo_questions()


@router.get("/knowledge/search")
def search_knowledge(
    q: str = Query(..., min_length=1, description="知识检索问题"),
    top_k: int = Query(5, ge=1, le=20, description="返回条数"),
) -> dict:
    """检索本地 ChromaDB 知识库。"""

    service = KnowledgeSearchService()
    context = service.search_structured(q, top_k=top_k)
    return {
        "query": q,
        "top_k": top_k,
        "matches": context.raw_matches,
        "retrieval_context": context.to_dict(),
    }


@router.post("/query", response_model=QueryResponse)
def query(request: QueryRequest) -> QueryResponse:
    """自然语言取数接口，首版只生成 SQL 和口径说明。"""

    composer = AnswerComposer()
    return composer.compose(
        request.question,
        session_id=request.session_id,
        use_memory=request.use_memory,
    )
