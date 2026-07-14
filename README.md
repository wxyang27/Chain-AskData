# Chain-AskData

Chain-AskData 是面向新氧连锁经管业务的自然语言取数（NL2SQL）MVP。

首版目标不是直接连接数仓执行查询，而是把自然语言问题转成可审计的 QueryPlan、标准口径说明、MaxCompute SQL 和校验结果。

## 当前能力

### 核心管道

- **意图路由**：自动分类问题为 nl2sql / schema_explain / caliber_explain / unknown，非取数问题不强制生成 SQL；`has_meaningful_evidence()` 防止仅指标噪音命中误判
- **Schema 检索**：三级索引（关键词/向量/Rerank）→ 混合检索 → SchemaGraph 构建
- **SchemaGraph 字段补全**：模板级依赖矩阵自动补入 `dp`/`is_valid`/`tenant_id`/维度字段/表关联关系，13 个模板全覆盖
- **QueryPlanCoT 四元组生成**：Qwen（百炼 `qwen-plus`）根据用户问题 + SchemaGraph 生成结构化四元组（数据库、处理对象、操作指令、输出目标），含本地校验 + 一次修复闭环 + 规则回退
- **SQL 生成**：
  - 模板 SQL：13 个 MVP Demo Query 的确定性 SQL 模板（始终可用）
  - LLM SQL（影子模式）：Qwen 根据已校验 CoT + SchemaGraph 生成 MaxCompute SQL
- **SQL 安全门禁**（规则门 + 业务口径门）：
  - SELECT/WITH only
  - 表、字段、JOIN 必须来自 SchemaGraph
  - `_d` / `_all_d` 快照表 `dp` 必须等于 `DATE_SUB(CURRENT_DATE(),1)`，禁止 `dp` 区间
  - 核销表 `is_valid=1` + `executed_date` 强制
  - 核销/支付业务日期上限必须到昨天，禁止包含 `CURRENT_DATE()`
  - “本月”统一为自然月 MTD：月初到昨天，禁止按最近 30 天替代
  - 城市、门店、品项、渠道、新老客维度使用标准字段：`city_name` / `sy_hospital_name` / `standard_name` / `cx_first_channel` / `is_new` 或 `is_pay_new`
  - 点名城市或品项时必须带对应过滤条件，防止漏筛
  - ORDER BY 必须有 LIMIT
  - 除法必须有 NULLIF 保护
  - MaxCompute 语法禁止：`DATE_TRUNC`/`INTERVAL`/`DATEADD`/`NOW()` 等
  - `DATE_SUB` 参数校验 + 本周日期语义校验
- **受控切换**：LLM SQL 通过安全门禁时采用（`sql_source="llm"`），失败时保留模板 SQL 兜底
- **口径说明输出**：固定结构的问题复述、QueryPlan 摘要、指标卡片、SQL、校验结果、口径说明、引用来源

### 前端界面

三栏 Web 页面：左侧输入 → 中间 QueryPlan + 检索轨迹 + SchemaGraph → 右侧模板 SQL / LLM SQL 双模块 + 结构对比表 + 校验结果。

### API 接口

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/query` | POST | 自然语言取数，返回 QueryPlan + SQL（模板/LLM）+ 校验 + 检索轨迹 |
| `/api/health` | GET | 健康检查 |
| `/api/demo-queries` | GET | 获取 13 条 Demo 问题列表 |
| `/api/knowledge/search` | GET | 知识库语义检索 |

`POST /api/query` 响应新增字段：

```json
{
  "sql": "当前使用的 SQL",
  "template_sql": "模板 SQL（始终保留）",
  "llm_sql": "Qwen 生成的 SQL",
  "llm_sql_adopted": true,
  "llm_sql_validation": { "passed": true, "errors": [], "used_tables": [...], "used_fields": [...] },
  "llm_sql_detail": { "generated": true, "explanation": "..." },
  "sql_source": "llm"
}
```

执行层字段：

```json
{
  "execution_enabled": false,
  "execution_mode": "disabled",
  "execution_status": "skipped",
  "sample_rows": [],
  "row_count": 0,
  "execution_error": "execution_disabled",
  "result_validation": {},
  "repair_attempt": {}
}
```

## 总体架构

项目按**离线 / 在线**分层，各层通过抽象接口解耦，可独立替换。

```
┌─────────────────────────────────────────────────────────┐
│  离线层（Offline）                                       │
│  Raw Word/Excel/YAML                                     │
│    → knowledge_importer → generated assets               │
│    → app.schema_indexing.build_indexes → schema indexes (8 JSON) │
│    → ChromaDB (897 chunks)                               │
│                                                          │
│  在线层（Online）                                        │
│  User Question                                           │
│    → Pipeline (13 observable stages)                     │
│      1. knowledge_retrieval  (keyword + vector + RRF)    │
│      2. semantic_contract    (业务语义归一)              │
│      3. schema_retrieval     (SchemaGraph 构建)          │
│      4. intent_route         (意图路由)                  │
│      5. query_plan           (QueryPlanCoT 生成)         │
│      6. template_sql         (模板 SQL)                  │
│      7. llm_sql              (Qwen SQL 生成 + 门禁)      │
│      8. sql_selection        (受控切换)                  │
│      9. sql_generation       (最终 SQL 归档)             │
│     10. sql_safety_gate      (静态安全门禁)              │
│     11. execution            (disabled/mock/sqlite)      │
│     12. result_validation    (结果形态校验)              │
│     13. repair_attempt       (修复 / 模板回退)           │
│    → QueryResponse (SQL + caliber + trace)               │
└─────────────────────────────────────────────────────────┘
```

### 可替换层

| 层 | 当前默认 | 可替换为 |
|----|---------|---------|
| **Embedding** | `HashEmbedding` (128-dim, 本地) | `DashScopeEmbedding` (text-embedding-v4, 1024-dim) |
| **Rerank** | `LightweightReranker` (词法) | `DashScopeRerank` (qwen-rerank / qwen3-rerank) |
| **SQL 执行** | `disabled`（默认不执行） | `mock` / `sqlite` / `MaxComputeExecutor` (ODPS 只读骨架) |
| **向量库** | `ChromaDB` (本地) | `Milvus` / `FAISS` / `PGVector` |

接口定义在 [app/model_clients/](app/model_clients/)，Pipeline 依赖接口而非具体实现。

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
- **Embedding**：MVP 阶段使用本地确定性 HashEmbedding（128 维），不依赖外部 Embedding 服务
- **检索策略**：HybridRetriever（关键词 + 向量 RRF 融合） + LightweightReranker

## 本地运行

```powershell
# 1. 离线构建索引与知识库（首次或资产变更后执行）
python -m app.schema_indexing.build_indexes

# 2. 查看资产质量报告
python -m app.schema_indexing.asset_report

# 3. 创建 .env 文件（参考 .env.example）

# 4. 启动服务
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

打开 `http://127.0.0.1:8000`

### SQL 执行层

默认不执行真实 SQL，保证 Demo 稳定：

```powershell
EXECUTION_MODE=disabled
```

需要展示闭环 Demo 时可切到 mock：

```powershell
EXECUTION_MODE=mock
```

API 会返回 `execution_enabled`、`execution_mode`、`execution_status`、`sample_rows`、`row_count`、`execution_error`。`sqlite` 模式预留给本地 demo DB，`maxcompute` 目前只保留只读执行骨架。

### 结果校验与修复闭环

执行层之后会进入轻量反馈闭环：

```text
SQL Safety Gate
  -> Execution
  -> Result Validation
  -> Repair Attempt
  -> Static Repair / Template Fallback
```

当前校验维度：

- SQL 是否执行失败
- 返回是否为空
- 返回列是否覆盖预期指标/维度
- 金额/人数类结果是否全为 NULL
- TOP 类问题是否同时具备 `ORDER BY + LIMIT`

如果执行反馈失败，系统会先根据 `RepairPolicy` 归因，再尝试 `StaticSqlRepairer`，修复后重新过 `SqlSafetyGate`；仍不可用时回退模板 SQL。Pipeline trace 中会记录 `sql_generation`、`sql_safety_gate`、`execution`、`result_validation`、`repair_attempt`。

## 测试

```powershell
# 快速测试（不含 LLM 调用）
pytest tests/ -q --ignore=tests/test_core6_verification.py

# 核心 6 问验收（含 LLM 调用，耗时较长）
pytest tests/test_core6_verification.py -v

# LLM SQL 专项测试
pytest tests/test_llm_sql.py -v

# 黄金评测集（需先启动本地服务，含 LLM 调用，耗时较长）
python eval/run_eval.py --api http://localhost:8000 --output eval/eval_result_YYYYMMDD.json
```

## 黄金评测集与当前基线

`eval/` 目录用于沉淀 NL2SQL 黄金评测集，不校验真实执行数值，重点校验意图、指标、表、字段、过滤条件、SQL 结构、口径说明和 critical rules。

| 文件 | 说明 |
|------|------|
| [eval/golden_eval_set.json](eval/golden_eval_set.json) | 46 条黄金评测样例，覆盖标准问法、同义改写、口径易混、组合问题、拒答边界、解释类问题 |
| [eval/run_eval.py](eval/run_eval.py) | 评测 runner，调用 `/api/query` 并输出通过率、失败归因、质量门槛 |
| [eval/README.md](eval/README.md) | 评测集设计、字段说明、质量门槛和运行方式 |
| [eval/eval_result_20260710_after_fix.json](eval/eval_result_20260710_after_fix.json) | 2026-07-10 第二次全量评测结果 |
| [eval/run_schema_retrieval_eval.py](eval/run_schema_retrieval_eval.py) | Schema 检索评测 runner |
| [eval/schema_retrieval_eval.json](eval/schema_retrieval_eval.json) | Schema 检索评测集（15 条） |
| [eval/schema_retrieval_eval_result.json](eval/schema_retrieval_eval_result.json) | Schema 检索最新评测结果 |

### Critical Rules

| 规则 | 要求 |
|------|------|
| CR001 | 快照表 `dp` 必须锁昨天，禁止区间 |
| CR002 | “本月”必须按自然月 MTD（月初到昨天） |
| CR003 | 城市维度/过滤必须使用 `city_name` |
| CR004 | 门店维度必须使用 `sy_hospital_name`（兼容 `tenant_alias_name`） |
| CR005 | 品项维度/过滤必须使用 `standard_name` |
| CR006 | 渠道维度/过滤必须使用 `cx_first_channel` |
| CR007 | 核销新老客使用 `is_new`，支付新老客使用 `is_pay_new` |

### Schema Retrieval v2：三层召回架构

检索不是黑盒，每个字段的来源可追溯：

```
raw_retrieval   → 关键词/向量/RRF/rerank 命中的字段（模型召回）
domain_closure  → 业务域自动补全的字段（dp/is_valid/pay_date/tenant_id 等）
metric_closure  → 指标级自动补全的字段（main_order_id/customer_id 等）
───────────────────────────────────────────────────
final_fields    → 最终进入 SchemaGraph 的字段
```

| 指标 | v1 (纯检索) | v2 (检索+闭包) |
|------|-----------|--------------|
| table_recall | 0.0% | **93.3%** |
| field_recall | 25.0% | **93.3%** |
| critical_field_recall | 53.9% | **100.0%** |
| relation_recall | 80.0% | 80.0% |

回归保护（CI 可执行）：
```
PYTHONPATH=. python eval/run_schema_retrieval_eval.py
# Guards: critical>=95%  field>=85%  table>=85%  passed>=14/15
```

### 2026-07-10 基线

| 指标 | 结果 |
|------|------|
| 主黄金集 | **46/46 (100.0%)** |
| 泛化补充集 | **10/10 (100.0%)** |
| Hard 通过率 | **100%** |
| Critical Rule | **79/79 (100.0%)** |

当前状态：**v1 基线固化。** 所有质量门槛全量通过。评测结果保存于 `eval/` 目录。

本轮新增能力：
- **意图路由**：自动分类 nl2sql / schema_explain / caliber_explain / unknown
- **品类泛化**：不限于模板 `revenue_category IN (...)`，支持自由品类过滤
- **待核销**：正确使用 `left_gmv` + `left_num > 0`，不混入支付日期过滤
- **0元占比**：`exe_income = 0` 核销域判断，不误用支付域 `pay_gmv = 0`
- **本周支付**：MaxCompute `WEEKDAY` 本周一到昨天，不写 `DATE_TRUNC`
- **新客核销人次占比**：`is_new = 1` 核销域，与支付域 `is_pay_new` 不混淆

## app 层目录导览

`app/` 是项目的在线问答主链路。当前整理方向是参考 `askdata_agent`：把“规划、检索、生成、校验、执行、反馈”拆成清晰模块，方便调试，也方便面试时按链路讲述。

```text
app/
  askdata_pipeline/     主编排层：串起 RAG、规划、SQL、执行、反馈，记录 Pipeline Trace
  cot_planning/         规划层：意图路由、语义契约、QueryPlan、QueryPlanCoT 生成与校验
  schema_indexing/      离线索引层：构建/加载 schema indexes，生成资产报告
  schema_retrieval/     在线检索层：根据问题召回字段/表/关系，组织 SchemaGraph 输入
  schema_graph/         Schema 图层：构建表字段关系图，做依赖字段闭包补全
  sql_generation/       SQL 生成层：模板 SQL + LLM SQL
  sql/                  SQL 治理层：validator、safety gate、static repairer
  execution/            SQL 执行层：disabled/mock/sqlite/maxcompute 执行路由
  feedback/             反馈层：结果校验、失败归因、修复/回退策略
  api/                  API 层：FastAPI 路由，核心入口 `/api/query`
  web/                  Web 层：轻量调试页面
  answer/               响应组装层：把 PipelineRunResult 组装成 API 返回
  core/                 配置层：环境变量、模型开关、执行模式
  models/               数据模型层：Pydantic / dataclass 请求响应结构
  metric_registry/      指标注册层：维护指标口径和模板映射
  model_clients/        模型客户端层：Embedding / Rerank provider 抽象与切换
  assets/               资产加载层：YAML/JSON 本地知识资产读取
  knowledge_importer/   知识导入底层：从 Word/Excel/reviewed yaml 生成结构化资产
  knowledge_indexer/    RAG 底层：ChromaDB、关键词检索、RRF、rerank
  llm/                  LLM 底层：OpenAI-compatible/Qwen client 与 prompt 基础设施
knowledge/
  examples/             Demo Query 资产
  metrics/              核心指标口径资产
  schema/               核心字段定义资产
  relations/            表关系资产
  tables/               核心表结构与口径资产
  generated/            批量导入的结构化资产（JSON）
  generated/indexes/    三级索引 JSON 文件（8 个）
static/                 前端静态资源
templates/              页面模板（三栏布局）
tests/                  测试（16 个文件，140+ 用例）
eval/                   黄金评测集、评测 runner 与基线结果
data/chroma/            ChromaDB 持久化存储
docs/
  primary_knowledge/    经管中心原始文档（Excel + Word）
  superpowers/plans/    实施计划文档
```

### app 主链路讲法

```text
API / Web
  -> AnswerComposer
  -> AskDataPipeline
  -> knowledge_retrieval      召回指标、字段、表、样例、风险提示
  -> semantic_contract        业务语义归一，锁定口径和必要字段
  -> schema_retrieval         构建本次问题需要的 SchemaGraph
  -> intent_route             区分取数、口径解释、字段解释、拒答
  -> query_plan               生成 QueryPlan / QueryPlanCoT
  -> template_sql + llm_sql   模板 SQL 保底，LLM SQL 影子生成
  -> sql_selection            LLM SQL 通过门禁才采用
  -> sql_safety_gate          静态校验 MaxCompute 语法、字段、口径、分区
  -> execution                默认 disabled，Demo 可切 mock/sqlite
  -> result_validation        校验执行失败、空结果、列缺失、全 NULL、TOP 形态
  -> repair_attempt           静态修复；仍失败则模板回退
  -> QueryResponse
```

面试时可以概括为：这个项目不是“让大模型直接写 SQL”，而是把自然语言取数拆成一条可观测的 RAG + Planning + SQL Governance Pipeline。RAG 负责找证据，Planning 负责约束业务理解，SQL Gate 负责守住口径和语法，Execution/Feedback 负责把生成结果变成可闭环 Demo。

## 重要约束

- 默认只生成 SQL 和口径说明；设置 `EXECUTION_MODE=mock/sqlite` 后可进入执行层闭环。
- SQL 只允许 `SELECT` 或 `WITH`。
- 使用 `soyoung_dw` 库名前缀。
- 查询 `_d` / `_all_d` 快照表必须带 `dp = DATE_SUB(CURRENT_DATE(),1)`，禁止把 `dp` 当业务日期区间。
- 出现 `ORDER BY` 必须带 `LIMIT`。
- 核销收入使用 `exe_income`，核销 GMV 使用 `exe_amount`。
- 核销人数使用 `customer_id`，核销人次使用 `verify_date_id`。
- 核销发生类问题使用 `executed_date`。
- 支付发生类问题使用 `pay_date`，并过滤 `is_paydate_cash = 0`。
- “本月”默认自然月 MTD：`DATETRUNC(CURRENT_DATE(), 'MONTH')` 到 `DATE_SUB(CURRENT_DATE(),1)`。
- 城市/大区通过 `tenant_id` 关联 `dim_qy_tenant_info_all_d`，使用 `city_name` / `area_name`。
- 品项使用 `standard_name`，渠道使用 `cx_first_channel`。
- 待核销金额是库存快照口径，默认不按 `pay_date` 截断。
- LLM SQL 禁止 `DATE_TRUNC`/`INTERVAL`/`NOW()` 等非 MaxCompute 语法。

## 开发进度

| 阶段 | 内容 | 状态 |
|------|------|------|
| Phase 0 | 代码框架搭建（FastAPI + Web UI + 数据模型） | ✅ 完成 |
| Phase 1 | 知识资产 + ChromaDB 初始化 | ✅ 完成 |
| Phase 2 | QueryPlan + 13 个 SQL 模板 + 校验器 | ✅ 完成 |
| Phase 3 | RAG 增强 + 意图路由 + Schema Graph + 混合检索 | ✅ 完成 |
| Phase 3.5 | 经管中心原始知识批量导入（762 chunks） | ✅ 完成 |
| Phase 4 | Qwen 接入：QueryPlanCoT 四元组生成 + 修复闭环 | ✅ 完成 |
| Phase 4.5 | SchemaGraph 依赖矩阵补全 + 校验器强化 | ✅ 完成 |
| Phase 5 | LLM SQL 影子模式 + 安全门禁 + 核心 6 问受控切换 | ✅ 完成 |
| Phase 5.5 | 黄金评测集 v1.2 + critical rules + 红榜归因基线 | ✅ 完成 |
| Phase 6 | DashScope Embedding/Rerank provider + 索引隔离 | ✅ 完成 |
| Phase 7 | SQL 执行层 + 结果校验 + 修复/回退闭环 | ✅ 完成 |
| Phase 8 | 长短期记忆（滑动窗口 + 向量检索引擎） | ⬜ 待开始 |

> 工作记录按日期追加，历史记录不覆盖。`2026-07-09` 保留为 LLM SQL 影子模式阶段基线，`2026-07-10` 记录评测集与硬规则治理的增量进展。

### 2026-07-09 工作记录

- **Qwen QueryPlanCoT**：`app/llm/` 模块建成，百炼 `qwen-plus` 根据 SchemaGraph 生成四元组，含本地校验 + 一次修复闭环 + 规则回退
- **SchemaGraph 字段补全**：`app/schema_graph/enricher.py` 模板级依赖矩阵自动补入 `dp`/`is_valid`/`tenant_id`/维度字段/表关联，13 模板全覆盖
- **RetrievalContext 去重**：`top_*()` 方法防止重复字段/指标/样例噪声
- **无关问题过滤**：`has_meaningful_evidence()` + IntentRouter 白名单双重判断
- **LLM SQL 影子模式**：`app/sql_generation/llm_generator.py` + `app/sql/safety_gate.py`，Qwen 根据 CoT + SchemaGraph 生成 SQL，经门禁检查
- **MaxCompute 语法约束**：Prompt + 门禁禁止 `DATE_TRUNC`/`INTERVAL`/`NOW()` 等非 MC 函数
- **受控切换**：核心 6 问（Q001-Q006）门禁通过时 `sql_source="llm"`，其余模板兜底
- **前端升级**：双 SQL 模块 + 结构对比表（表/JOIN/WHERE/GROUP BY/ORDER BY/LIMIT 六维对比）
- **测试**：14 条 CoT 测试 + 21 条 SQL 测试 + 31 条核心 6 实验收 → 140+ passed

### 2026-07-10 工作记录

- **黄金评测集 v1.2**：在 2026-07-09 LLM SQL 影子模式基础上，新增 46 条评测样例，覆盖 7 条 critical rules、13 Demo 扩展、同义改写、口径易混、组合查询、拒答边界和解释类问题
- **评测 runner 强化**：`eval/run_eval.py` 支持 critical rule 自动推断、质量门槛、`sql_source` / `llm_sql_adopted` / 安全门错误检查和失败归因
- **硬规则安全门**：`dp` 昨天分区、MTD、城市过滤、品项过滤、维度分组、新老客字段、业务日期上限等规则已进入 `SqlSafetyGate`
- **维度管理能力**：支持品项、门店、城市、渠道、新老客维度的 SchemaGraph 补字段、QueryPlan 后处理和 SQL 安全校验
- **本月口径**：“本月”统一归一为自然月 MTD（月初到昨天），不再按最近 30 天处理
- **基线结果**：第二次全量评测 25/46，critical rules 79/79，组合类问题 9/9
- **下一步红榜**：优先修复待核销 `left_num > 0`、支付域 `is_paydate_cash = 0`、品类 `revenue_category`、支付/核销双域问题、拒答边界和口径解释完整性

## 技术栈

Python 3.14 · FastAPI · Pydantic · ChromaDB 1.0+ · 阿里云百炼 Qwen · pytest · 原生 HTML/CSS/JS
