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
- **SQL 安全门禁**（9 项检查）：
  - SELECT/WITH only
  - 表、字段、JOIN 必须来自 SchemaGraph
  - 快照表 dp 分区过滤（支持别名/裸字段/比较运算符）
  - 核销表 `is_valid=1` + `executed_date` 强制
  - ORDER BY 必须有 LIMIT
  - 除法必须有 NULLIF 保护
  - MaxCompute 语法禁止：`DATE_TRUNC`/`INTERVAL`/`DATEADD`/`NOW()` 等
  - `DATE_SUB` 参数校验 + 本周日期语义校验
- **受控切换**：核心 6 问（Q001-Q006）门禁通过时自动采用 LLM SQL（`sql_source="llm"`），其余模板兜底
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
# 创建 .env 文件（参考 .env.example）
# 启动服务
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

打开 `http://127.0.0.1:8000`

## 测试

```powershell
# 快速测试（不含 LLM 调用）
pytest tests/ -q --ignore=tests/test_core6_verification.py

# 核心 6 问验收（含 LLM 调用，耗时较长）
pytest tests/test_core6_verification.py -v

# LLM SQL 专项测试
pytest tests/test_llm_sql.py -v
```

## 目录说明

```text
app/
  api/                  API 路由
  answer/               响应组装（AnswerComposer 编排全流程）
  assets/               本地知识资产加载（YAML/JSON）
  core/                 环境变量配置
  intent_router/        意图路由（nl2sql / schema_explain / caliber_explain / unknown）
  knowledge_importer/   原始知识批量导入（Excel/Word → JSON 资产）
  knowledge_indexer/    ChromaDB 知识库、混合检索、Rerank、RetrievalContext
  llm/                  Qwen 适配层
    local_client.py       OpenAI 兼容客户端（SSL + 错误诊断）
    prompts.py            QueryPlanCoT 系统提示词
    query_plan_cot_generator.py  CoT 四元组生成 + 解析 + 修复闭环
    query_plan_cot_validator.py  本地 SchemaGraph 约束校验（字段/关系/跨表/输出接地）
    sql_generator.py      LLM SQL 生成器（影子模式）
    sql_safety_gate.py    SQL 安全门禁（9 项检查 + MaxCompute 语法约束）
  metric_registry/      指标注册
  models/               数据模型
  query_planner/        QueryPlan 规划（模板匹配 + RAG 增强 + CoT）
  schema_graph/         SchemaGraph 构建 + 字段补全（依赖矩阵）
  schema_index/         三级索引构建与加载
  schema_retrieval/     Schema 检索（AskData 风格）
  sql_generator/        SQL 模板生成（13 个确定性模板）
  sql_validator/        SQL 安全与口径校验
  web/                  页面路由
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
| Phase 6 | 语义 Embedding + DataWorks/MaxCompute 只读执行 | ⬜ 待开始 |
| Phase 7 | SQL 修复闭环 + 结果校验与回调修正 | ⬜ 待开始 |
| Phase 8 | 长短期记忆（滑动窗口 + 向量检索引擎） | ⬜ 待开始 |

### 2026-07-09 工作记录

- **Qwen QueryPlanCoT**：`app/llm/` 模块建成，百炼 `qwen-plus` 根据 SchemaGraph 生成四元组，含本地校验 + 一次修复闭环 + 规则回退
- **SchemaGraph 字段补全**：`app/schema_graph/enricher.py` 模板级依赖矩阵自动补入 `dp`/`is_valid`/`tenant_id`/维度字段/表关联，13 模板全覆盖
- **RetrievalContext 去重**：`top_*()` 方法防止重复字段/指标/样例噪声
- **无关问题过滤**：`has_meaningful_evidence()` + IntentRouter 白名单双重判断
- **LLM SQL 影子模式**：`app/llm/sql_generator.py` + `app/llm/sql_safety_gate.py`，Qwen 根据 CoT + SchemaGraph 生成 SQL，经 9 项门禁检查
- **MaxCompute 语法约束**：Prompt + 门禁禁止 `DATE_TRUNC`/`INTERVAL`/`NOW()` 等非 MC 函数
- **受控切换**：核心 6 问（Q001-Q006）门禁通过时 `sql_source="llm"`，其余模板兜底
- **前端升级**：双 SQL 模块 + 结构对比表（表/JOIN/WHERE/GROUP BY/ORDER BY/LIMIT 六维对比）
- **测试**：14 条 CoT 测试 + 21 条 SQL 测试 + 31 条核心 6 实验收 → 140+ passed

## 技术栈

Python 3.14 · FastAPI · Pydantic · ChromaDB 1.0+ · 阿里云百炼 Qwen · pytest · 原生 HTML/CSS/JS
