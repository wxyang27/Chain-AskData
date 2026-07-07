# 意图路由 + Schema Graph + QueryPlanCoT + 混合检索 实施计划

> **给后续执行者：** 本计划用于在保持当前模板优先 NL2SQL 路径稳定的前提下，新增 AskData-lite 风格的意图路由、Schema Graph、QueryPlanCoT 规划步骤和混合检索能力。执行时按任务逐项推进，每步都要可运行、可测试。

**目标：** 新增意图路由、Schema Graph、QueryPlanCoT 规划步骤和混合检索，同时保持当前模板优先的 NL2SQL 主路径稳定。

**架构：** 请求流水线扩展为 `KnowledgeSearchService → IntentRouter → SchemaGraphBuilder → QueryPlanner → SqlGenerator / ExplainAnswer`。Schema Graph 作为 SQL 生成和解释型响应的共享结构化上下文。混合检索在不拆分 Chroma Collection 的前提下，提升 RetrievalContext 分组前的召回率。

**技术栈：** FastAPI、Pydantic、ChromaDB、pytest、本地 YAML 资产。

---

### 任务 1：意图路由

**涉及文件：**
- 新建：`app/intent_router/router.py`
- 修改：`app/models/query.py`
- 修改：`app/answer/composer.py`
- 测试：`tests/test_intent_router.py`
- 测试：`tests/test_answer_modes.py`

- [ ] 先写失败测试，覆盖 `schema_explain`（表/字段解释）、`caliber_explain`（口径解释）、`unknown`（无法识别）和 `nl2sql`（正常取数）四种意图。
- [ ] 基于问题文本 + RetrievalContext 证据实现确定性路由规则。
- [ ] 改造 `AnswerComposer`，explain / unknown 意图返回解释型响应，不强制生成 SQL。
- [ ] 运行针对性测试和全量测试。

### 任务 2：Schema Graph 结构化图谱

**涉及文件：**
- 新建：`app/schema_graph/graph.py`
- 新建：`app/schema_graph/builder.py`
- 修改：`app/models/query.py`
- 测试：`tests/test_schema_graph.py`

- [ ] 先写失败测试，验证从 RetrievalContext 中正确构建表、字段、关系、指标、缺失证据和图谱文本。
- [ ] 实现 `SchemaGraphBuilder.build(retrieval_context)`。
- [ ] 将图谱文本纳入 QueryResponse，供 UI 和 API 追踪展示。
- [ ] 运行针对性测试和全量测试。

### 任务 3：QueryPlanCoT 思维链规划

**涉及文件：**
- 修改：`app/models/query.py`
- 修改：`app/query_planner/planner.py`
- 测试：`tests/test_query_plan_cot.py`

- [ ] 先写失败测试，要求 `query_plan.query_plan_cot` 包含对象识别、字段选择、过滤条件、计算逻辑、输出格式和规划证据六个步骤。
- [ ] 基于 demo 模板 + SchemaGraph 实现确定性 QueryPlanCoT 生成。
- [ ] 保持现有 SQL 生成器与 QueryPlan 字段的向后兼容。
- [ ] 运行针对性测试和全量测试。

### 任务 4：混合检索

**涉及文件：**
- 新建：`app/knowledge_indexer/keyword_extractor.py`
- 新建：`app/knowledge_indexer/hybrid_retriever.py`
- 修改：`app/knowledge_indexer/service.py`
- 测试：`tests/test_hybrid_retriever.py`

- [ ] 先写失败测试，覆盖关键词提取、RRF（倒数排名融合）和结构化搜索对字段/指标命中的保留。
- [ ] 实现基于当前本地 chunks 的关键词检索 + Chroma 向量检索双路径。
- [ ] 使用 RRF 算法融合两路候选，再经现有轻量 reranker 精排。
- [ ] 运行针对性测试和全量测试。

### 最终验证

- [ ] `python -m unittest discover -s tests -v`
- [ ] `python -m app.knowledge_indexer.init_chroma`
- [ ] API 冒烟测试：对 `/api/query` 分别发送一条 NL2SQL 取数问题、一条 Schema 解释问题、一条口径解释问题、一条无法识别的模糊问题，确认四种意图均返回正确结构。
