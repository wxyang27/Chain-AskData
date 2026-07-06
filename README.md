# Chain-AskData

Chain-AskData 是面向新氧连锁经管业务的自然语言取数 MVP。

首版目标不是直接连接数仓执行查询，而是把自然语言问题转成可审计的查询计划、标准口径说明、MaxCompute SQL 和校验结果。

## 当前能力

- FastAPI 后端服务
- 简单 Web 页面
- 自然语言问题接口：`POST /api/query`
- 健康检查接口：`GET /api/health`
- QueryPlan 查询计划
- 门店核销收入 TOP10 的首个确定性 Demo 链路
- SQL 安全与口径校验

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

## 目录说明

```text
app/
  api/              API 路由
  answer/           响应组装
  core/             配置
  metric_registry/  指标注册
  models/           数据模型
  query_planner/    QueryPlan 规划
  schema_retrieval/ Schema 检索
  sql_generator/    SQL 生成
  sql_validator/    SQL 校验
  web/              页面路由
knowledge/          业务知识资产
static/             前端静态资源
templates/          页面模板
tests/              测试
```

## 重要约束

- 首版只生成 SQL，不真实执行。
- SQL 只允许 `SELECT` 或 `WITH`。
- 使用 `soyoung_dw` 库名前缀。
- `_all_d` 表必须带 `dp` 分区。
- 出现 `ORDER BY` 必须带 `LIMIT`。
- 核销收入使用 `exe_income`。
- 门店展示优先使用 `sy_hospital_name`。
