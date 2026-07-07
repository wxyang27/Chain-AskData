# Chain-AskData

Chain-AskData 是面向新氧连锁经管业务的自然语言取数（NL2SQL）MVP。

首版目标不是直接连接数仓执行查询，而是把自然语言问题转成可审计的 QueryPlan、标准口径说明、MaxCompute SQL 和校验结果。

## 当前能力

### 核心管道

- **意图路由**：自动分类问题为 nl2sql / schema_explain / caliber_explain / unknown，非取数问题不强制生成 SQL
- **混合检索**：关键词 + 向量 RRF 融合，在 RetrievalContext 分组前提升召回率
- **QueryPlan + QueryPlanCoT**：生成结构化查询计划，包含对象、字段、过滤、计算、输出和证据步骤
- **Schema Graph**：从检索上下文构建表、字段、关系、指标的结构化图谱，供 SQL 生成和解释响应共享
- **SQL 生成**：13 个 MVP Demo Query 的确定性 SQL 模板（模板优先，DeepSeek 回退预留）
- **SQL 校验**：安全校验 + 业务口径校验（只读、dp 分区、LIMIT、表白名单、核销/支付/渗透率口径、敏感字段）
- **口径说明输出**：固定结构的问题复述、QueryPlan 摘要、指标卡片、SQL、校验结果、口径说明、引用来源

### API 接口

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/query` | POST | 自然语言取数，返回 QueryPlan + SQL + 校验 + 检索轨迹 |
| `/api/health` | GET | 健康检查 |
| `/api/demo-queries` | GET | 获取 13 条 Demo 问题列表 |
| `/api/knowledge/search` | GET | 知识库语义检索（关键词 + 向量融合 + 轻量 Rerank） |

### 前端界面

Codex 风格三栏 Web 页面：左侧输入 → 中间 QueryPlan + 检索轨迹（按指标/字段/表/关系/样例分组） → 右侧 SQL + 校验结果。

## MVP Demo Query

1. 昨天整体核销收入、核销GMV、核销人次、核销人数、核销客单价是多少？
2. 最近30天各门店核销收入 TOP10
3. 本周私域新客核销收入是多少？
4. 最近30天私域、公域、老带新的核销收入、人次、客单价对比
5. 最近30天新客和老客核销收入、人次、客单价分别是多少？
6. 最近30天大单品、常规品、大师团核销收入对比
7. 最近30天品项核销收入 TOP20
8. 最近90天奇迹胶原品项渗透率是多少？
9. 最近30天0元单数量和核销人数是多少？
10. 截至昨天各门店待核销金额 TOP10
11. 最近30天新客支付GMV、支付人数、支付客单价是多少？
12. 最近60天支付后30日核销率是多少？
13. 最近30天升单人数、升单核销人次、升单核销收入是多少？

## 知识资产

### 核心资产（手写口径）

| 资产 | 路径 | 说明 |
|------|------|------|
| 核心指标 | [knowledge/metrics/core_metrics.yaml](knowledge/metrics/core_metrics.yaml) | 11 条权威指标口径（公式、来源表、过滤条件、易错提醒） |
| 核心字段 | [knowledge/schema/core_fields.yaml](knowledge/schema/core_fields.yaml) | 28 个关键字段定义（业务含义、口径说明、风险提示） |
| 核心表 | [knowledge/tables/core_tables.yaml](knowledge/tables/core_tables.yaml) | 9 张核心表的表结构与口径规则 |
| 表关系 | [knowledge/relations/table_relations.yaml](knowledge/relations/table_relations.yaml) | 表间 JOIN 关系与使用场景 |
| Demo 问题 | [knowledge/examples/demo_queries.json](knowledge/examples/demo_queries.json) | 13 条 Demo 问题（case_id、template_id、指标、维度、风险标记） |

### 批量导入资产（从经管中心原始文档解析）

> 导入模块位于 [app/knowledge_importer/](app/knowledge_importer/)，从 [docs/primary_knowledge/](docs/primary_knowledge/) 读取 Excel 和 Word 源文档。

| 资产 | 路径 | 数量 |
|------|------|------|
| 指标（原子 + 衍生） | [knowledge/generated/metrics_full.json](knowledge/generated/metrics_full.json) | 151 |
| 用户画像字段 | [knowledge/generated/user_profile_fields.json](knowledge/generated/user_profile_fields.json) | 112 |
| 维度 | [knowledge/generated/dimensions.json](knowledge/generated/dimensions.json) | 10 |
| 数据源 | [knowledge/generated/data_sources.json](knowledge/generated/data_sources.json) | 7 |
| 看板指标映射 | [knowledge/generated/dashboard_metrics.json](knowledge/generated/dashboard_metrics.json) | 288 |
| 库表 | [knowledge/generated/tables_full.json](knowledge/generated/tables_full.json) | 49 |
| 业务分析 Playbook | [knowledge/generated/business_playbooks.json](knowledge/generated/business_playbooks.json) | 81 |

### ChromaDB 知识库

- **知识块总数**：762 chunks（核心 64 + 批量导入 698）
- **持久化目录**：`data/chroma`
- **目标 Collection**：`chain_askdata_knowledge`
- **类型化 Collection**：`metric_schema_collection`、`table_field_schema_collection`、`sql_example_collection`
- **Embedding**：MVP 阶段使用本地确定性 HashEmbedding（128 维），不依赖外部服务
- **检索策略**：HybridRetriever（关键词 + 向量 RRF 融合） + LightweightReranker（词法重排 + 字段/术语加权）
- **加载策略**：`load_knowledge_chunks()` 默认仅加载核心 MVP 知识，避免大知识库噪声影响核心 QueryPlan；`include_generated=True` 时加载批量导入资产

## 本地运行

```powershell
python -m uvicorn app.main:app --reload
```

打开：

```text
http://127.0.0.1:8000
```

## 测试

```powershell
pytest -q
```

当前状态：**59 passed, 1 warning**（含 API 契约、管道业务正确性、校验规则、意图路由、Schema Graph、QueryPlanCoT、混合检索、ChromaDB 知识库、原始知识导入、生成块加载等 15 个测试文件）。

## ChromaDB 知识库初始化

初始化命令：

```powershell
python -m app.knowledge_indexer.init_chroma
```

默认写入位置：

```text
data/chroma
```

默认 collection：

```text
chain_askdata_knowledge
```

可通过环境变量覆盖：

```powershell
$env:CHROMA_PERSIST_DIR="data/chroma"
$env:CHROMA_COLLECTION_NAME="chain_askdata_knowledge"
```

检索示例：

```text
GET /api/knowledge/search?q=核销客单价的分母是什么&top_k=3
```

返回结果包含：

- `document`：命中的知识块文本
- `metadata`：资产类型、指标编码、表名、模板 ID 等结构化信息
- `distance`：Chroma 原始距离
- `rerank_score`：轻量 rerank 分数

`POST /api/query` 也会返回 `retrieval_trace` 和 `retrieval_context`，用于展示本次取数问题命中的知识块（按指标/字段/表/关系/样例分类）。RAG 检索结果现已正式参与 QueryPlan 的指标选择、字段选择、模板选择和风险提示生成。

## 目录说明

```text
app/
  api/                  API 路由
  answer/               响应组装（AnswerComposer 编排全流程）
  assets/               本地知识资产加载（YAML/JSON，lru_cache）
  core/                 环境变量配置
  intent_router/        意图路由（nl2sql / schema_explain / caliber_explain / unknown）
  knowledge_importer/   原始知识批量导入（Excel/Word → JSON 资产 → Chroma chunks）
  knowledge_indexer/    ChromaDB 知识库初始化、检索与 Rerank
  metric_registry/      指标注册
  models/               数据模型（QueryRequest、QueryPlan、QueryPlanCoT、QueryResponse 等）
  query_planner/        QueryPlan 规划（模板匹配 + RAG 增强 + CoT 步骤）
  schema_graph/         Schema 结构化图谱（表/字段/关系/指标 + 缺失证据）
  schema_retrieval/     Schema 检索（MVP 本地 YAML 查找）
  sql_generator/        SQL 生成（13 个确定性模板）
  sql_validator/        SQL 安全与口径校验（7 项检查规则）
  web/                  页面路由
knowledge/
  examples/             Demo Query 资产
  metrics/              核心指标口径资产
  schema/               核心字段定义资产
  relations/            表关系资产
  tables/               核心表结构与口径资产
  generated/            批量导入的结构化资产（JSON）
static/                 前端静态资源
templates/              页面模板（Codex 风格三栏布局）
tests/                  测试（15 个文件，59 个用例）
data/chroma/            ChromaDB 持久化存储
docs/
  primary_knowledge/    经管中心原始文档（Excel + Word）
  superpowers/plans/    实施计划文档
```

## 重要约束

- 首版只生成 SQL，不真实执行。
- SQL 只允许 `SELECT` 或 `WITH`。
- 使用 `soyoung_dw` 库名前缀。
- 查询 `soyoung_dw` 表必须带 `dp` 分区。
- 出现 `ORDER BY` 必须带 `LIMIT`。
- 核销收入使用 `exe_income`，核销 GMV 使用 `exe_amount`。
- 核销人数使用 `customer_id`，核销人次使用 `verify_date_id`。
- 核销发生类问题使用 `executed_date`。
- 支付发生类问题使用 `pay_date`，并过滤 `is_paydate_cash = 0`。
- 待核销金额是库存快照口径，默认不按 `pay_date` 截断。
- 品项经营优先使用 `standard_name`。
- 门店展示优先使用 `sy_hospital_name`，主键使用 `tenant_id`。

## 开发进度

| 阶段 | 内容 | 状态 |
|------|------|------|
| Phase 0 | 代码框架搭建（FastAPI + Web UI + 数据模型） | ✅ 完成 |
| Phase 1 | 知识资产 + ChromaDB 初始化 | ✅ 完成 |
| Phase 2 | QueryPlan + 13 个 SQL 模板 + 校验器 | ✅ 完成 |
| Phase 3 | RAG 增强 + 意图路由 + Schema Graph + 混合检索 | ✅ 完成 |
| Phase 3.5 | 经管中心原始知识批量导入（762 chunks） | ✅ 完成 |
| Phase 4 | 评估与优化 | ⬜ 待开始 |
| Phase 5 | 08 版本（语义 Embedding + 检索路径统一 + LLM 回退） | ⬜ 待开始 |

## 技术栈

Python 3.14 · FastAPI · Pydantic · ChromaDB 1.0+ · openpyxl · python-docx · pytest · 原生 HTML/CSS/JS
