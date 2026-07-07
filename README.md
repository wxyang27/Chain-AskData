# Chain-AskData

Chain-AskData 是面向新氧连锁经管业务的自然语言取数 MVP。

首版目标不是直接连接数仓执行查询，而是把自然语言问题转成可审计的 QueryPlan、标准口径说明、MaxCompute SQL 和校验结果。

## 当前能力

- FastAPI 后端服务
- 简单 Web 页面
- 自然语言取数接口：`POST /api/query`
- Demo 问题接口：`GET /api/demo-queries`
- 知识库检索接口：`GET /api/knowledge/search`
- 健康检查接口：`GET /api/health`
- 13 个 MVP Demo Query 的确定性 SQL 模板
- 指标、表、关系、样例问题的机器可读资产
- SQL 安全与业务口径校验

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
python -m unittest discover -s tests -v
```

## ChromaDB 知识库初始化

当前版本已支持把 `knowledge/` 下的指标、表、关系、Demo Query 资产写入本地 ChromaDB。

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

MVP 阶段使用本地确定性 hash embedding，避免初始化时依赖外部 embedding 服务。后续可替换为 Qwen、DeepSeek 或其他 embedding 服务。

检索示例：

```text
GET /api/knowledge/search?q=核销客单价的分母是什么&top_k=3
```

返回结果包含：

- `document`：命中的知识块文本
- `metadata`：资产类型、指标编码、表名、模板 ID 等结构化信息
- `distance`：Chroma 原始距离
- `rerank_score`：轻量 rerank 分数

`POST /api/query` 也会返回 `retrieval_trace`，用于展示本次取数问题命中的知识块。目前 trace 只做可观测和调试，不直接改变 SQL 生成结果。

## 目录说明

```text
app/
  api/              API 路由
  answer/           响应组装
  assets/           本地知识资产加载
  core/             配置
  knowledge_indexer/ ChromaDB 知识库初始化与检索
  metric_registry/  指标注册
  models/           数据模型
  query_planner/    QueryPlan 规划
  schema_retrieval/ Schema 检索
  sql_generator/    SQL 生成
  sql_validator/    SQL 校验
  web/              页面路由
knowledge/
  examples/         Demo Query 资产
  metrics/          指标口径资产
  relations/        表关系资产
  tables/           表结构与口径资产
static/             前端静态资源
templates/          页面模板
tests/              单元测试
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
