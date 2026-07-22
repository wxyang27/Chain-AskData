# Chain-AskData

Chain-AskData 是一个面向新氧连锁医美经营分析场景的 **Agentic Text2SQL / Schema RAG 问数系统**。

它将自然语言经营问题转化为可审计、可执行、可校验的 MaxCompute SQL，并通过 Hybrid Schema RAG、QueryPlanCoT、SQL Safety Gate、真实执行、结果校验与修复回退机制，降低 LLM-SQL 在字段幻觉、口径混淆、漏过滤、漏分组等场景下的风险。

一句话概括：

> 这不是一个“让大模型直接写 SQL”的工具，而是一条可观测、可执行、可回退的 Agentic Text2SQL Workflow。

当前链路已经覆盖从短期记忆追问补全、业务问题理解、指标/字段召回、QueryPlanCoT、SQL 生成、安全门禁、MaxCompute 只读执行、结果校验到修复回退的闭环。LLM SQL 默认以受控方式参与：可以生成候选 SQL，但只有通过 Safety Gate、执行层和结果校验后才会被采纳；否则系统会继续使用规则修复或模板 SQL 兜底。飞书 CatData 机器人也已接入，支持私聊/群聊 @ 触发、Card 2.0 图表回复、SQL 折叠展示和运行日志写入飞书多维表格。

---

## 1. 项目背景

连锁医美经营分析中，业务问题通常包含大量隐含约束：

- 指标口径：核销收入、核销 GMV、支付 GMV、待核销金额、0 元单、支付后 30 日核销率
- 业务域：核销域、支付域、库存快照、门店维度、品项维度、渠道维度、新老客维度
- 数仓字段：`exe_income`、`exe_amount`、`pay_gmv`、`left_gmv`、`standard_name`、`sy_hospital_name`
- 强约束：`dp` 分区、`is_valid=1`、`pay_date` / `executed_date`、`city_name`、`LIMIT N`

如果只让 LLM 直接从自然语言生成 SQL，很容易出现：

- 字段选错：把核销收入写成 GMV，或把支付域字段用于核销域
- 过滤漏掉：问题问“北京奇迹胶原 TOP5”，SQL 没有 `city_name` / `standard_name`
- 分组漏掉：问题问“各门店”，SQL 只聚合总数
- 语法不兼容：生成非 MaxCompute 函数，如 `DATE_TRUNC`、`INTERVAL`、`NOW()`
- 校验误杀：SQL 业务正确，但因为 `total_income` 和“核销收入”列名不同被误判失败

因此本项目的目标是构建一个 **可解释、可校验、可修复、可回退** 的 LLM-SQL 闭环，而不是追求一次生成即正确。

---

## 2. 项目目标

项目面向连锁经营分析中的自然语言取数需求，目标是把业务指标口径、数仓表结构、历史 SQL 经验和执行校验能力沉淀成一条稳定可复用的问数链路：

- 让业务同事用自然语言描述问题，系统自动识别指标、维度、时间范围和过滤条件
- 支持同一会话内的短追问补全，让“那上海呢”“top3”“本月呢”可以继承最近问题的指标和分析对象
- 通过指标字典、schema 索引和样例 SQL 降低字段幻觉与口径混淆
- 用 Keyword、BM25、Vector、RRF、Rerank 组合召回表、字段和指标证据
- 用 Thinking / Coder 模型分工，把业务规划和 SQL 生成拆开治理
- 同时保留模板 SQL、规则修复 SQL、LLM SQL 三种来源，兼顾稳定性和泛化能力
- 通过 SQL Safety Gate、真实执行、结果校验、修复回退闭环提升返回结果可信度
- 保留 Pipeline Trace，让每一步可观测、可解释、可复盘

---

## 3. 核心能力

### 3.1 自然语言到 SQL

- 支持连锁经营常见取数问题
- 输出 QueryPlan、SQL、口径说明、校验结果、执行结果和 Pipeline Trace
- 支持模板 SQL 与 LLM SQL 双路径

### 3.2 Hybrid Schema RAG

- Keyword Retrieval：业务词典、字段名、别名精确命中
- BM25 Retrieval：词法相关性召回
- Vector Retrieval：Embedding 语义召回
- RRF Fusion：多路召回结果融合
- Rerank：候选 schema 重排
- Closure：补齐 `dp`、`is_valid`、`pay_date`、`tenant_id` 等低语义但 SQL 必需字段

### 3.3 QueryPlanCoT

- 识别意图、业务域、指标、维度、过滤条件、时间范围
- 生成结构化四元组：
  - 数据库
  - 处理对象
  - 操作指令
  - 输出目标
- 在生成前注入当前可用数据库和工具能力，约束模型只能在已暴露能力范围内规划
- `processing_objects` 要覆盖指标字段、筛选字段、分组/输出字段、业务日期字段、分区字段、口径字段和必要 join key
- `operation_instructions` 按筛选、关联、聚合/计算、排序/截断、输出的顺序描述执行计划

### 3.4 Thinking / Coder 模型分工

- Thinking Model：负责业务理解、口径规划、QueryPlanCoT
- Coder Model：负责根据 QueryPlan 和 SchemaGraph 生成 SQL，不决定数据库连接或执行路由
- Embedding Model：负责 schema / metric / example 向量召回
- Rerank Model：负责候选字段、表、指标重排

### 3.5 SQL 安全门禁

- 只允许 `SELECT` / `WITH`
- 表、字段、JOIN 必须来自 SchemaGraph
- 快照表必须带 `dp = DATE_SUB(CURRENT_DATE(),1)`
- 核销域强制 `is_valid = 1`
- 核销发生类问题使用 `executed_date`
- 支付发生类问题使用 `pay_date` 和 `is_paydate_cash`
- 点名城市、品项、门店时必须保留对应字段和过滤条件
- TOP 类问题必须包含 `ORDER BY + LIMIT`
- 点名城市、品项等文本筛选时使用 `REGEXP` 或 `LIKE`，避免标准名称带后缀时精确等值无法命中
- 禁止非 MaxCompute 语法函数

### 3.6 执行层闭环

支持四种执行模式：

```text
disabled    默认不执行，适合稳定演示
mock        返回模拟结果，适合离线调试
sqlite      预留本地样例 DB 执行
maxcompute  通过 PyODPS 只读执行真实 MaxCompute SQL
```

执行请求携带 `database` 作为路由元信息，当前默认暴露 `soyoung_dw`。SQL 生成模型只生成 SQL，执行层根据已校验的 `database` 和执行模式选择对应 executor；如果请求的数据库未注册，执行层会拒绝执行。

### 3.7 Result Validation / Repair / Fallback

- 校验执行失败、空结果、返回列缺失、金额/人数全 NULL、TOP 形态
- 支持字段语义等价：
  - `sy_hospital_name ≈ 门店`
  - `total_income / income / exe_income ≈ 核销收入`
- 支持用户约束保真：
  - 问题有“北京”，SQL 必须保留 `city_name`
  - 问题有“奇迹胶原”，SQL 必须保留 `standard_name`
  - 问题有“TOP5”，SQL 必须 `LIMIT 5`
- LLM SQL 失败时先规则修复，仍失败再模板兜底

---

## 4. 总体架构

项目按**离线 / 在线**分层，各层通过抽象接口解耦，可独立替换。

```text
┌─────────────────────────────────────────────────────────┐
│  离线层（Offline）                                       │
│  Raw Word/Excel/YAML                                     │
│    → knowledge_importer → generated assets               │
│    → app.schema_indexing.build_indexes → schema indexes (8 JSON) │
│    → ChromaDB (897 chunks)                               │
│                                                          │
│  在线层（Online）                                        │
│  User Question                                           │
│    → Pipeline (14 observable stages)                     │
│      1. memory_resolution   (短期记忆追问补全，可选)     │
│      2. knowledge_retrieval (keyword + BM25 + vector + RRF + rerank) │
│      3. semantic_contract   (业务语义归一)               │
│      4. schema_retrieval    (SchemaGraph 构建)           │
│      5. intent_route        (意图路由)                   │
│      6. query_plan          (能力边界注入 + QueryPlanCoT 生成) │
│      7. template_sql        (模板 SQL)                   │
│      8. llm_sql             (Qwen SQL 生成 + 门禁)       │
│      9. sql_selection       (受控切换)                   │
│     10. sql_generation      (最终 SQL 归档)              │
│     11. sql_safety_gate     (静态安全门禁)               │
│     12. execution           (disabled/mock/sqlite/maxcompute) │
│     13. result_validation   (结果形态校验)               │
│     14. repair_attempt      (修复 / 模板回退)            │
│    → QueryResponse (SQL + caliber + execution + trace)   │
└─────────────────────────────────────────────────────────┘
```

更细的在线链路：

```text
API / Web
  -> AskDataPipeline
  -> memory_resolution
  -> knowledge_retrieval
  -> semantic_contract
  -> schema_retrieval
  -> intent_route
  -> query_plan      # 含可用数据库与工具能力注入
  -> template_sql
  -> llm_sql
  -> sql_selection
  -> sql_generation
  -> sql_safety_gate
  -> execution
  -> result_validation
  -> repair_attempt
  -> QueryResponse
```

---

## 5. 模型分层

当前项目不是“一把梭”调用同一个大模型，而是按任务拆分模型角色。

```text
User Question
  -> Hybrid Retrieval
       Embedding: text-embedding-v4 或本地 HashEmbedding
       Rerank: qwen-rerank / qwen3-rerank 或 LightweightReranker
  -> CoT Planning
       Thinking Model: LLM_THINKING_MODEL / LLM_COT_MODEL
  -> SQL Generation
       Coder Model: LLM_CODER_MODEL / LLM_SQL_MODEL
  -> SQL Safety Gate
       表、字段、JOIN、dp、业务日期、MaxCompute 语法校验
  -> Execution Router
       disabled / mock / sqlite / maxcompute(PyODPS)
  -> Reflection
       Result Validation -> Static Repair -> Safety Gate -> Template Fallback
```

推荐配置：

```env
LLM_PROVIDER=dashscope
LLM_COT_MODEL=qwen-plus
LLM_SQL_MODEL=qwen-plus

LLM_THINKING_MODEL=qwen3-vl-30b-a3b-thinking
LLM_CODER_MODEL=qwen3-coder-next

EMBEDDING_PROVIDER=dashscope
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_DIMENSION=1024

RERANK_PROVIDER=dashscope
RERANK_MODEL=qwen3-rerank
```

设计说明：

本项目把大模型能力拆成四层：Embedding 负责找 schema 证据，Rerank 负责候选重排，Thinking 模型负责业务规划和口径拆解，Coder 模型负责 SQL 生成。后续再接 Safety Gate、Execution 和 Result Validation，因此系统不是让大模型直接裸写 SQL，而是通过可观测、可回退的 Agentic Workflow 控制查询风险。

---

## 6. 目录结构

```text
app/
  askdata_pipeline/     主编排层：串起 RAG、规划、SQL、执行、反馈，记录 Pipeline Trace
  memory/               短期记忆层：保存最近 3 轮结构化状态，完成追问补全和回指选择
  cot_planning/         规划层：意图路由、语义契约、QueryPlan、QueryPlanCoT
  schema_indexing/      离线索引层：构建/加载 schema indexes，生成资产报告
  schema_retrieval/     在线检索层：召回字段/表/关系，组织 SchemaGraph 输入
  schema_graph/         Schema 图层：构建表字段关系图，做依赖字段闭包补全
  sql_generation/       SQL 生成层：模板 SQL + LLM SQL
  sql/                  SQL 治理层：validator、safety gate、static repairer
  execution/            SQL 执行层：disabled/mock/sqlite/maxcompute 执行路由
  feedback/             反馈层：结果校验、失败归因、修复/回退策略
  api/                  API 层：FastAPI 路由，核心入口 /api/query
  feishu_bot/           飞书入口层：长连接机器人、意图分类、Card 2.0 回复、Base 日志写入
  web/                  Web 层：轻量调试页面
  answer/               响应组装层：把 PipelineRunResult 组装成 API 返回
  core/                 配置层：环境变量、模型开关、执行模式
  models/               数据模型层：Pydantic / dataclass 请求响应结构
  metric_registry/      指标注册层：维护指标口径和模板映射
  model_clients/        模型客户端层：Embedding / Rerank provider 抽象与切换
  assets/               资产加载层：YAML/JSON 本地知识资产读取
  knowledge_importer/   知识导入底层：从 Word/Excel/reviewed yaml 生成结构化资产
  knowledge_indexer/    RAG 底层：ChromaDB、关键词检索、BM25、RRF、rerank
  llm/                  LLM 底层：OpenAI-compatible/Qwen client 与 prompt 基础设施

knowledge/
  examples/             示例 Query 资产
  metrics/              核心指标口径资产
  schema/               核心字段定义资产
  relations/            表关系资产
  tables/               核心表结构与口径资产
  generated/            批量导入的结构化资产
  generated/indexes/    离线索引 JSON

eval/                   黄金评测集、schema retrieval 评测、评测 runner
tests/                  单元测试与链路测试
static/                 前端静态资源
templates/              前端页面模板
data/chroma/            ChromaDB 持久化存储
docs/                   原始知识文档与项目过程文档
```

---

## 7. 快速开始

### 7.1 安装依赖

```powershell
pip install -r requirements.txt
```

### 7.1.1 Windows 终端中文显示

本项目文档和源码统一使用 UTF-8。若在 Windows PowerShell 中看到中文乱码，可先执行：

```powershell
chcp 65001
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
Get-Content -Raw -Encoding UTF8 README.md
```

测试入口已在 `pyproject.toml` 中配置 `pythonpath = ["."]`，通常可直接运行 `pytest`。

### 7.2 配置环境变量

```powershell
copy .env.example .env
```

在 `.env` 中填写模型和执行层配置。不要把真实 API Key、AccessKey 提交到 GitHub。

### 7.3 构建离线索引

```powershell
python -m app.schema_indexing.build_indexes
```

### 7.4 查看资产报告

```powershell
python -m app.schema_indexing.asset_report
```

### 7.5 启动服务

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

如果 8000 端口被占用，可使用：

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

打开：

```text
http://127.0.0.1:8000
```

### 7.6 终端调试短期记忆

短期记忆使用进程内 dict 保存最近 3 轮结构化状态，形成轻量滑动窗口。传入同一个 `session_id` 后，可以支持换品项、换城市、换渠道、换排名和换时间等追问补全。

默认情况下，短追问继承最近一轮；只有用户明确说“回到/还是/刚才第一个/北京那个”等回指表达时，才从窗口中选择更早的匹配轮次。

```powershell
python -m app.memory_cli --session local
```

示例：

```text
AskData> 最近30天北京奇迹胶原核销收入 TOP5门店
AskData> 那上海呢
AskData> top3
AskData> 北京那个，换成奇迹童颜
AskData> 本月
```

终端会输出原始问题、补全后的问题、是否使用记忆、窗口大小、继承轮次、template_id、sql_source 和最终 SQL。

开启 `LLM_ENABLED=true` 后，补全后的用户问题和结构化硬约束会同步进入 LLM SQL prompt；Safety Gate 会继续检查城市、品项、渠道、本月时间窗和 TopN/LIMIT 是否被保留。城市和品项名称要求使用 `REGEXP` 或 `LIKE` 模糊匹配，避免 `city_name = '杭州'` 无法命中 `杭州市` 这类标准名称；只有通过门禁的 LLM SQL 才会被采纳。

### 7.7 启动飞书 CatData 机器人

当前飞书入口使用 **长连接模式**，不需要公网域名或回调 URL。配置好飞书应用的 App ID / App Secret 后，直接启动：

```powershell
python -m app.feishu_bot.runner
```

启动成功后，日志会显示 CatData 机器人身份和 WebSocket 连接信息。私聊会直接响应；群聊默认只响应明确 @CatData 的消息。

停止进程：

```powershell
Get-Process python | Stop-Process
```

---

## 8. 配置说明

### 8.1 LLM 配置

```env
LLM_PROVIDER=dashscope
LLM_API_KEY=your_dashscope_api_key

LLM_COT_MODEL=qwen-plus
LLM_SQL_MODEL=qwen-plus

LLM_THINKING_MODEL=qwen3-vl-30b-a3b-thinking
LLM_CODER_MODEL=qwen3-coder-next
```

说明：

- `LLM_THINKING_MODEL` 用于 QueryPlanCoT
- `LLM_CODER_MODEL` 用于 LLM SQL Generation
- 如果某个模型无权限或不存在，Pipeline Trace 会显示 HTTP 错误和 fallback 状态

### 8.2 Embedding / Rerank 配置

默认可使用本地 HashEmbedding 和 LightweightReranker，不依赖外部服务。

切换 DashScope：

```env
DASHSCOPE_API_KEY=your_dashscope_api_key

EMBEDDING_PROVIDER=dashscope
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_DIMENSION=1024

RERANK_PROVIDER=dashscope
RERANK_MODEL=qwen3-rerank
```

注意：

- Embedding 模型切换后，需要重建向量索引
- Rerank 如果未开通权限，应 graceful fallback 到本地 reranker

### 8.3 执行层配置

默认不执行真实 SQL：

```env
EXECUTION_MODE=disabled
```

可切换为：

```env
EXECUTION_MODE=mock
EXECUTION_MODE=sqlite
EXECUTION_MODE=maxcompute
```

MaxCompute 只读执行配置：

```env
EXECUTION_MODE=maxcompute
ODPS_ACCESS_ID=your_odps_access_id
ODPS_SECRET_ACCESS_KEY=your_odps_secret_access_key
ODPS_PROJECT_NAME=soyoung_dw
ODPS_ENDPOINT=http://service.cn-beijing.maxcompute.aliyun.com/api
```

安全约束：

- 只允许 `SELECT` / `WITH`
- 禁止 DDL / DML
- 默认限制返回样例行
- 凭证只从 `.env` 读取，不写入 README 或 `.env.example`

### 8.4 飞书 CatData 机器人配置

飞书入口需要在 `.env` 中配置以下变量：

```env
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=your_feishu_app_secret
FEISHU_REPLY_ENABLED=true
FEISHU_CARD_ENABLED=true
FEISHU_GROUP_REQUIRE_MENTION=true
FEISHU_RAW_EVENT_LOG=false
```

说明：

- `FEISHU_APP_ID` / `FEISHU_APP_SECRET`：飞书应用的 App ID 和 App Secret，必须配置。
- `FEISHU_CARD_ENABLED=true`：优先使用飞书 Card 2.0 回复；如果卡片发送失败，会自动回退为 Markdown。
- `FEISHU_GROUP_REQUIRE_MENTION=true`：群聊中只有明确 @CatData 时才回复，避免机器人在群里误触发。
- `FEISHU_RAW_EVENT_LOG=true`：仅用于排查收不到消息、@ 识别等问题，日常建议关闭。
- 当前为长连接接入，不需要公网域名，也不需要配置 `https://域名/api/lark/events` 回调地址。

可选：将运行日志写入飞书多维表格：

```env
FEISHU_LOG_ENABLED=true
FEISHU_LOG_BASE_TOKEN=your_base_token
FEISHU_LOG_TABLE_ID=your_table_id
FEISHU_LOG_CLI=lark-cli
FEISHU_LOG_IDENTITY=user
```

日志写入依赖 `lark-cli` 用户授权，至少需要 `base:record:create` scope。授权后，机器人会把时间、用户、对话类型、问题、意图、回复摘要、SQL、执行状态、耗时和错误信息写入 Base。

### 8.5 飞书卡片展示策略

CatData 的飞书回复使用 Card 2.0，并针对经营数据场景做了轻量展示：

- TOP/排行类结果：优先用绿色横向条形图展示，长门店名在图表下方以紧凑明细保留。
- SQL：放入 `SQL` 折叠面板，默认收起，并按 `SELECT / FROM / JOIN / WHERE / GROUP BY / ORDER BY / LIMIT` 等关键字格式化换行。
- 闲聊或非问数问题：返回固定边界话术，说明 CatData 的定位和可支持的问题范围。
- 卡片发送失败时：自动回退为 Markdown，保证用户仍能收到答案。

---

## 9. SQL 生成策略

当前系统保留三类 SQL 来源。

| SQL 类型 | 使用场景 | 优点 | 风险 |
|---|---|---|---|
| 模板 SQL | 高频标准问题，如“最近30天各门店核销收入 TOP10” | 稳定、可控、适合兜底 | 泛化弱，容易漏掉临时条件 |
| 规则/修复 SQL | SQL 大体正确但缺字段、日期函数、口径过滤、别名或约束 | 能保留细粒度条件并补齐工程规则 | 只能处理确定性修复 |
| LLM SQL | 条件组合复杂、模板覆盖不住的问题 | 泛化强，适合临时组合查询 | 可能漏字段、漏分组、别名不标准 |

SQL 生成模型只负责把已校验的 QueryPlanCoT 和 SchemaGraph 转成 MaxCompute SQL，不决定连接哪个数据库。`database` 是执行路由元信息，由规划阶段在能力边界内给出，并由执行层校验和消费。

LLM SQL 采纳链路：

```text
LLM SQL
  -> SQL Safety Gate
  -> Execution
  -> Result Validation
  -> Static / Rule Repair
  -> Safety Gate 再校验
  -> Template Fallback
```

当前项目对 LLM SQL 的兜底不是“失败就回模板”，而是：

1. 先规则修复，尽量保留用户细粒度条件
2. 再模板兜底，保证系统稳定返回

典型案例：

```text
问题：最近30天北京奇迹胶原核销收入 TOP5门店

旧问题：
  LLM SQL 业务正确，但 Result Validation 只做列名字面匹配，
  把 total_income / sy_hospital_name 误判为不符合“核销收入 / 门店”，
  触发 template_fallback，导致北京、奇迹胶原、TOP5 条件丢失。

修复后：
  sql_source = llm
  llm_sql_adopted = true
  execution_mode = maxcompute
  execution_status = success
  row_count = 5
  result_validation.passed = true
```

设计说明：

SQL 生成不是只靠模板，也不是盲信 LLM。标准问题用模板保证稳定，复杂组合问题用 LLM 提升泛化，中间用规则层做修复和口径约束，最后由 Safety Gate、真实执行和 Result Validation 决定是否采纳。

---

## 10. RAG 检索链路

Text2SQL 的 Schema RAG 和普通文档 RAG 不完全一样。普通文档 RAG 更关注语义相似，但 Schema RAG 必须精确召回字段、表和口径。

例如：

- “支付 GMV”必须命中 `pay_gmv`
- “核销收入”必须命中 `exe_income`
- “支付发生日期”必须命中 `pay_date`
- “核销有效记录”必须补齐 `is_valid`

当前检索链路：

```text
用户问题
  -> Keyword Retrieval       字段名、业务词、别名 exact/contains match
  -> BM25 Lexical Retrieval  词频、逆文档频率、文档长度
  -> Vector Retrieval        Embedding 语义召回
  -> RRF Fusion              多路召回按排名融合
  -> Rerank                  本地 rerank 或 DashScope qwen-rerank
  -> Closure                 domain_closure / metric_closure 补齐必需字段
  -> SchemaGraph
```

当前融合策略采用等权 RRF：

```text
RRF score(d) = Σ 1 / (k + rank_i(d))
```

这样做的原因：

- Keyword、BM25、Vector 的原始分数不在同一量纲
- RRF 只看排名，早期更稳定、更可解释
- 多路都靠前的字段会自然获得更高融合分

字段来源可追溯：

```text
raw_retrieval   -> keyword/BM25/vector/RRF/rerank 命中的字段
domain_closure  -> 业务域补全字段，如 dp/is_valid/pay_date/tenant_id
metric_closure  -> 指标级补全字段，如 main_order_id/customer_id
final_fields    -> 最终进入 SchemaGraph 的字段
```

设计说明：

Text2SQL 对字段精确性要求很高，因此系统没有只依赖向量检索。Keyword 负责确定性字段名和业务术语，BM25 负责词法召回，Embedding 负责语义召回，再用 RRF 融合并 rerank。最后用业务闭包补齐 `dp`、`is_valid` 这类不容易被语义召回但 SQL 必需的字段。

---

## 11. 结果校验与修复闭环

SQL 通过静态门禁不等于业务答案正确，因此执行后还要做结果校验。

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
- TOP 类问题是否具备 `ORDER BY + LIMIT`
- 字段语义等价是否成立
- 用户问题里的城市、品项、门店、TOP N 是否被 SQL 保留

示例：

```text
sy_hospital_name ≈ 门店
total_income / income / exe_income ≈ 核销收入
```

```text
问题有“北京” -> SQL 必须包含 city_name
问题有“奇迹胶原” -> SQL 必须包含 standard_name
问题有“门店” -> SQL 必须包含门店字段并 GROUP BY
问题有 TOP5 -> SQL 必须 LIMIT 5
```

失败处理：

1. `RepairPolicy` 归因
2. `StaticSqlRepairer` 尝试修复
3. 修复 SQL 重新过 `SqlSafetyGate`
4. 仍不可用则回退模板 SQL
5. Pipeline Trace 记录 `result_validation` 和 `repair_attempt`

---

## 12. 测试与评估

### 12.1 单元测试与链路测试

```powershell
# 快速测试
pytest tests/ -q --ignore=tests/test_core6_verification.py

# API + 执行层 + 结果校验闭环
pytest tests/test_api.py tests/test_execution_layer.py tests/test_feedback_loop.py -q

# LLM SQL 专项测试
pytest tests/test_llm_sql.py -v

# 飞书 Card 2.0 展示结构测试
pytest tests/test_feishu_cards.py -q
```

### 12.2 黄金评测集

```powershell
python eval/run_eval.py --api http://localhost:8000 --output eval/eval_result_latest.json
```

评测关注：

- intent 是否正确
- 指标、维度、字段、表是否正确
- SQL 是否包含必要过滤条件
- Critical Rules 是否通过
- 口径说明是否覆盖关键业务术语

### 12.3 LLM SQL 采纳评估

LLM SQL 的评估重点不是“是否生成了 SQL”，而是候选 SQL 能否通过 Safety Gate 并被最终采纳。Prompt 调整时建议使用同一批 golden case 做前后对比，关注：

- `generated`：LLM 是否成功返回 SQL
- `gate_passed`：SQL 是否通过静态安全门禁
- `llm_sql_adopted`：候选 SQL 是否被最终链路采用
- `sql_source`：最终采用 `llm`、`template`、`template_fallback` 还是 `*_repaired`

最近一次只调整 QueryPlanCoT 和 SQL 生成提示词后，在 P0 前 10 条样本上，LLM SQL 生成保持 10/10，采纳从 6/10 提升到 8/10。对应报告保存在：

```text
eval/prompt_eval_before_sample10.json
eval/prompt_eval_after_sample10.json
```

### 12.4 Schema Retrieval 评测

```powershell
PYTHONPATH=. python eval/run_schema_retrieval_eval.py
```

关键指标：

```text
critical_field_recall
field_recall
table_recall
relation_recall
```

当前 schema retrieval 通过闭包补齐后，核心目标是保证：

```text
critical_field_recall >= 95%
field_recall >= 85%
table_recall >= 85%
```

---

## 13. 示例问题

```text
最近30天北京奇迹胶原核销收入 TOP5门店
昨天整体核销收入、核销GMV、核销人次、核销人数、核销客单价是多少？
最近30天各门店核销收入 TOP10
最近30天私域、公域、老带新的核销收入、人次、客单价对比
最近30天新客和老客核销收入、人次、客单价分别是多少？
最近30天大单品、常规品、大师团核销收入对比
最近30天品项核销收入 TOP20
最近90天奇迹胶原品项渗透率是多少？
最近30天0元单数量和核销人数是多少？
截至昨天各门店待核销金额 TOP10
最近30天新客支付GMV、支付人数、支付客单价是多少？
最近60天支付后30日核销率是多少？
最近30天升单人数、升单核销人次、升单核销收入是多少？
本月奇迹胶原核销收入时间进度达成率
本月奇迹童颜核销收入时间进度达成率
本月BBL HERO核销收入时间进度达成率
本月新一代热玛吉核销收入时间进度达成率
```

---

## 14. 当前限制

- 当前主要面向新氧连锁医美经营分析场景，迁移到其他行业需要重建 schema / metric / example 资产
- MaxCompute 真实执行依赖只读账号和网络环境，默认关闭真实执行
- LLM SQL 仍可能漏掉隐含业务约束，因此必须经过 Safety Gate、Execution、Result Validation
- 当前前端是调试型页面，重点展示 Pipeline Trace，不追求生产 BI 交互体验
- 当前 RRF 采用等权融合，后续可基于 Recall@K、Precision@K、MRR 调 Weighted RRF
- Rerank 模型可能受 DashScope 权限影响，未开通时会 fallback 到本地 reranker
- 当前结果校验偏结构校验，真实数值正确性仍需要业务侧或数据侧进一步验证

---

## 15. Roadmap

短期：

- 增加更多复杂组合问题到 golden eval
- 将最近 3 轮短期记忆从终端调试入口逐步接入 Web/API 和飞书入口
- 强化 LLM SQL 的 constraint-aware prompt、Safety Gate 和静态修复，持续提升可采纳率
- 扩展 Result Validation 对诊断类问题、占比类问题、对比类问题的校验
- 丰富城市、品项、渠道、时间窗、TopN 等追问改写规则和回指识别样例

中期：

- 增加字段血缘和指标依赖图展示
- 引入更多统计评估指标，如 Recall、Precision、MRR、Correctness
- 将 MaxCompute 执行结果进一步接入解释层，支持结果摘要和异常诊断
- 对 Weighted RRF、DashScope Embedding、DashScope Rerank 做 A/B 评估
- 在 Capability Context 基础上扩展多数据源注册结构，为 `soyoung_analysis` 等受控数据源预留路由能力
- 将真实问答日志、最终采用 SQL、修复轨迹和用户反馈沉淀为可复用评测集

长期：

- 在最近 3 轮滑动窗口基础上补充摘要压缩、用户偏好和组织级指标记忆
- 将 schema 检索、指标查询、SQL 校验、SQL 执行封装为标准化工具能力
- 基于高质量问答与修复样例探索 SFT、偏好优化或小模型蒸馏
- 从当前 Agentic Workflow 演进为可权限治理、可复盘、可持续学习的数据分析 Agent

---

## API

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/query` | POST | 自然语言问数，返回 QueryPlan、SQL、执行结果、校验结果、Pipeline Trace |
| `/api/health` | GET | 健康检查 |
| `/api/demo-queries` | GET | 示例问题列表 |
| `/api/knowledge/search` | GET | 知识库检索 |

核心响应字段：

请求示例：

```json
{
  "question": "那上海呢",
  "session_id": "local",
  "use_memory": true
}
```

```json
{
  "sql": "最终采用的 SQL",
  "original_question": "用户原始问题",
  "resolved_question": "短期记忆补全后的问题",
  "session_id": "会话 ID",
  "memory_used": true,
  "template_sql": "模板 SQL",
  "llm_sql": "LLM 生成 SQL",
  "llm_sql_adopted": true,
  "sql_source": "llm",
  "execution_enabled": true,
  "execution_mode": "maxcompute",
  "execution_status": "success",
  "sample_rows": [],
  "row_count": 5,
  "result_validation": {},
  "repair_attempt": {},
  "pipeline_trace": {}
}
```

字段说明：

```text
sql              最终采用 SQL，可能来自 template、LLM 或 fallback
original_question 用户原始问题
resolved_question  进入 Pipeline 的实际问题；无追问时等于原始问题
memory_used        是否使用短期记忆完成追问补全
template_sql     模板 SQL
llm_sql          LLM 影子 SQL，用于对比和门禁评估
llm_sql_adopted  LLM SQL 是否被最终采用
sql_source       最终 SQL 来源：template / llm / template_fallback / *_repaired
execution_mode   disabled / mock / sqlite / maxcompute
```

---

## 技术栈

```text
Python 3.14
FastAPI
Pydantic
ChromaDB
DashScope / 阿里云百炼 Qwen
PyODPS / MaxCompute
Feishu / Lark Card 2.0
lark-channel-sdk
BM25
RRF
Rerank
pytest
HTML / CSS / JavaScript
```
