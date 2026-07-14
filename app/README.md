# app 模块导览

`app/` 是 Chain-AskData 的在线问答主链路。当前项目不是把 LLM 直接接到 SQL，而是把自然语言取数拆成一条可观测、可回退的 Text2SQL Pipeline。

## 一句话主链路

```text
API / Web
  -> AnswerComposer
  -> AskDataPipeline
  -> Knowledge Retrieval
  -> Semantic Contract
  -> Schema Retrieval / SchemaGraph
  -> Intent Route
  -> QueryPlanCoT
  -> Template SQL + LLM SQL
  -> SQL Safety Gate / Static Repair
  -> Execution
  -> Result Validation / Repair Attempt
  -> QueryResponse
```

## 入口层

| 模块 | 职责 |
|---|---|
| `main.py` | 创建 FastAPI 应用，挂载 API / Web / static |
| `api/` | 对外 REST API，核心入口是 `/api/query` |
| `web/` | 轻量调试页面路由 |
| `answer/` | 响应组装层，把 PipelineRunResult 转成 QueryResponse |

`answer/` 不再负责主链路编排。主链路已经收敛到 `askdata_pipeline/`。

## 编排层

| 模块 | 职责 |
|---|---|
| `askdata_pipeline/objects.py` | PipelineRunResult、PipelineTrace、PipelineStageLog |
| `askdata_pipeline/pipeline.py` | AskDataPipeline 主编排，每个 `_stage_*` 对应一个可观测阶段 |

面试讲述时可以把 `askdata_pipeline/` 作为项目骨架核心：它回答“一个问题进来之后系统到底经历了哪些步骤”。

## 检索层

| 模块 | 职责 |
|---|---|
| `schema_indexing/` | 离线 schema index 构建与加载，连接知识导入和 Chroma 构建 |
| `knowledge_indexer/` | 通用 RAG 检索，融合知识块、字段、指标、样例和风险信息 |
| `schema_retrieval/` | AskData 风格 Schema 检索入口，把检索结果转成 SchemaGraph |
| `schema_graph/` | 构建可给 CoT/SQL 使用的结构化 Schema 子图，并补全依赖字段 |

这几层的关系：

```text
knowledge_indexer 负责召回证据
schema_indexing 负责构建/读取离线索引
schema_retrieval 负责选择相关 schema
schema_graph 负责组织成可用的表字段关系图
```

## 规划层

| 模块 | 职责 |
|---|---|
| `cot_planning/` | 判断意图、归一语义契约、生成 QueryPlan，并接入 QueryPlanCoT |
| `metric_registry/` | 指标口径注册与读取 |

规划层解决的问题不是写 SQL，而是先判断：

- 用户到底是不是在取数。
- 这是什么业务域。
- 需要哪些指标、维度、过滤条件。
- 哪些字段是高风险必需字段。

## SQL 层

| 模块 | 职责 |
|---|---|
| `sql_generation/` | SQL 生成层，包含确定性模板 SQL 与 LLM SQL |
| `sql/` | SQL safety gate / validator / repairer |
| `execution/` | SQL 执行层接口，支持 disabled/mock/sqlite/maxcompute 骨架 |
| `feedback/` | 执行结果校验与修复策略，把失败反馈转成 repair/fallback 动作 |

当前策略是双轨：

```text
Template SQL 始终可用
LLM SQL 只有通过 Safety Gate 才被采用
失败时回退到 Template SQL
Execution 默认 disabled；面试 Demo 可切 mock 返回样例结果
Result Validation 负责检查执行失败、空结果、列缺失、全 NULL 和 TOP 形态
Repair Attempt 负责静态修复和模板回退
```

## 模型与配置层

| 模块 | 职责 |
|---|---|
| `llm/local_client.py` | OpenAI-compatible Chat Client |
| `cot_planning/query_plan_cot_generator.py` | QueryPlanCoT 生成与修复 |
| `cot_planning/query_plan_cot_validator.py` | QueryPlanCoT 本地约束校验 |
| `model_clients/` | Embedding / Rerank 抽象接口，预留 DashScope 切换 |
| `core/config.py` | 环境变量配置 |

`model_clients/` 当前主要是 Embedding / Rerank 接口抽象；SQL 执行接口收敛在 `execution/`，便于讲清“生成 SQL”和“执行 SQL”的边界。

## 资产层

| 模块 | 职责 |
|---|---|
| `assets/` | YAML / JSON 资产加载 |
| `knowledge_importer/` | 从 Word / Excel / reviewed yaml 导入结构化知识 |
| `models/` | Pydantic API 模型和 QueryPlan 数据结构 |

## 新手阅读顺序

建议按这个顺序读代码：

1. `api/routes.py`：看请求如何进入系统。
2. `answer/composer.py`：看最终响应如何组装。
3. `askdata_pipeline/pipeline.py`：看完整主链路。
4. `askdata_pipeline/objects.py`：看 trace 和 run result。
5. `schema_indexing/README.md`：看离线索引层。
6. `schema_retrieval/askdata_style_retriever.py`：看 SchemaGraph 如何生成。
7. `cot_planning/planner.py`：看 QueryPlan / CoT 如何生成。
8. `sql/README.md`：看 SQL 为什么能被采纳、修复或拒绝。

## 面试讲述版本

可以这样概括：

> 我把自然语言取数拆成可观测 Pipeline。系统先通过 RAG 召回指标、字段、表和样例，再构建 SchemaGraph；随后用语义契约和 QueryPlanCoT 约束模型理解，最后生成模板 SQL 和 LLM SQL。LLM SQL 不是直接采用，而是经过 SQL Safety Gate 和静态修复，失败时回退到模板 SQL。这样兼顾了业务口径准确性和 LLM 泛化能力。
