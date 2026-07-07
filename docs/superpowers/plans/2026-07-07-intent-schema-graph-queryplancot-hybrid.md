# 意图路由 + Schema Graph + QueryPlanCoT + 混合检索 实施计划

> **给后续执行者：**本计划用于在保持当前模板优先 NL2SQL 路径稳定的前提下，新增 AskData-lite 风格的意图路由、Schema Graph、QueryPlanCoT 规划步骤和混合检索。

**目标：**新增意图路由、Schema Graph、QueryPlanCoT 规划步骤和混合检索，同时保持当前模板优先的 NL2SQL 主路径稳定。

**架构：**请求流水线变为 `KnowledgeSearchService -> IntentRouter -> SchemaGraphBuilder -> QueryPlanner -> SqlGenerator/ExplainAnswer`。Schema Graph 是 SQL 生成和解释响应的共享结构化上下文。混合检索在不拆分 Chroma Collection 的前提下提升 RetrievalContext 分组前的召回率。

**技术栈：**FastAPI、Pydantic、ChromaDB、pytest、本地 YAML 资产。

---

### 任务 1：意图路由

**文件：**
- 新建：`app/intent_router/router.py`
- 修改：`app/models/query.py`
- 修改：`app/answer/composer.py`
- 测试：`tests/test_intent_router.py`
- 测试：`tests/test_answer_modes.py`

- [ ] 先写测试，覆盖 `schema_explain`、`caliber_explain`、`unknown`、`nl2sql` 四种意图。
- [ ] 实现基于问题文本 + RetrievalContext 证据的确定性路由。
- [ ] 让 `AnswerComposer` 在 explain/unknown 意图时返回解释响应，不强制生成 SQL。
- [ ] 运行针对性测试和全量测试。

### 任务 2：Schema Graph

**文件：**
- 新建：`app/schema_graph/graph.py`
- 新建：`app/schema_graph/builder.py`
- 修改：`app/models/query.py`
- 测试：`tests/test_schema_graph.py`

- [ ] 先写测试，验证从 RetrievalContext 构建表、字段、关系、指标、缺失证据和 graph 文本。
- [ ] 实现 `SchemaGraphBuilder.build(retrieval_context)`。
- [ ] 在 QueryResponse 中包含 graph 文本，供 UI/API 追踪。
- [ ] 运行针对性测试和全量测试。

### 任务 3：QueryPlanCoT

**文件：**
- 修改：`app/models/query.py`
- 修改：`app/query_planner/planner.py`
- 测试：`tests/test_query_plan_cot.py`

- [ ] 先写测试，要求 `query_plan.query_plan_cot` 包含对象、字段、过滤、计算、输出和证据步骤。
- [ ] 实现基于 demo 模板 + SchemaGraph 的确定性 QueryPlanCoT 生成。
- [ ] 保持现有 SQL 生成器与当前 QueryPlan 字段兼容。
- [ ] 运行针对性测试和全量测试。

### 任务 4：混合检索

**文件：**
- 新建：`app/knowledge_indexer/keyword_extractor.py`
- 新建：`app/knowledge_indexer/hybrid_retriever.py`
- 修改：`app/knowledge_indexer/service.py`
- 测试：`tests/test_hybrid_retriever.py`

- [ ] 先写测试，覆盖关键词提取、RRF 融合、结构化搜索保留字段/指标命中。
- [ ] 实现基于当前本地 chunks 的关键词检索 + Chroma 向量检索。
- [ ] 使用 RRF 和现有轻量 reranker 融合候选结果。
- [ ] 运行针对性测试和全量测试。

### 验证

- [ ] `python -m unittest discover -s tests -v`
- [ ] `python -m app.knowledge_indexer.init_chroma`
- [ ] API 冒烟测试：`/api/query` 分别测试一条 NL2SQL 问题、一条 schema 解释问题、一条口径解释问题、一条未知意图问题。
