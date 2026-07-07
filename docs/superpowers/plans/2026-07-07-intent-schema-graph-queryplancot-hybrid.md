# Intent Schema Graph QueryPlanCoT Hybrid Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add AskData-lite intent routing, Schema Graph, QueryPlanCoT planning steps, and hybrid retrieval while keeping the current template-first NL2SQL path stable.

**Architecture:** The request flow becomes `KnowledgeSearchService -> IntentRouter -> SchemaGraphBuilder -> QueryPlanner -> SqlGenerator/ExplainAnswer`. Schema Graph is the shared structured context for SQL generation and explanation responses. Hybrid retrieval improves recall before RetrievalContext grouping without splitting Chroma collections yet.

**Tech Stack:** FastAPI, Pydantic, ChromaDB, unittest, local JSON-compatible YAML assets.

---

### Task 1: Intent Router

**Files:**
- Create: `app/intent_router/router.py`
- Modify: `app/models/query.py`
- Modify: `app/answer/composer.py`
- Test: `tests/test_intent_router.py`
- Test: `tests/test_answer_modes.py`

- [ ] Write failing tests for `schema_explain`, `caliber_explain`, `unknown`, and `nl2sql`.
- [ ] Implement deterministic routing from question text plus RetrievalContext evidence.
- [ ] Make `AnswerComposer` return explanation responses without forcing SQL for explain/unknown intents.
- [ ] Run targeted tests and full suite.

### Task 2: Schema Graph

**Files:**
- Create: `app/schema_graph/graph.py`
- Create: `app/schema_graph/builder.py`
- Modify: `app/models/query.py`
- Test: `tests/test_schema_graph.py`

- [ ] Write failing tests that build tables, fields, relations, metrics, missing evidence, and graph text from RetrievalContext.
- [ ] Implement `SchemaGraphBuilder.build(retrieval_context)`.
- [ ] Include graph text in QueryResponse for UI/API trace.
- [ ] Run targeted tests and full suite.

### Task 3: QueryPlanCoT

**Files:**
- Modify: `app/models/query.py`
- Modify: `app/query_planner/planner.py`
- Test: `tests/test_query_plan_cot.py`

- [ ] Write failing tests requiring `query_plan.query_plan_cot` with objects, fields, filters, calculation, output, and evidence.
- [ ] Implement deterministic QueryPlanCoT generation from demo template plus SchemaGraph.
- [ ] Keep existing SQL generator compatible with current QueryPlan fields.
- [ ] Run targeted tests and full suite.

### Task 4: Hybrid Retrieval

**Files:**
- Create: `app/knowledge_indexer/keyword_extractor.py`
- Create: `app/knowledge_indexer/hybrid_retriever.py`
- Modify: `app/knowledge_indexer/service.py`
- Test: `tests/test_hybrid_retriever.py`

- [ ] Write failing tests for keyword extraction, RRF fusion, and structured search preserving field/metric hits.
- [ ] Implement keyword retrieval using current local chunks plus Chroma vector retrieval.
- [ ] Fuse candidates using RRF and existing lightweight reranker.
- [ ] Run targeted tests and full suite.

### Verification

- [ ] `python -m unittest discover -s tests -v`
- [ ] `python -m app.knowledge_indexer.init_chroma`
- [ ] API smoke test for `/api/query` with one NL2SQL question, one schema explain question, one caliber explain question, and one unknown question.
