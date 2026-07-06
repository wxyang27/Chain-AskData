# Chain-AskData 代码框架搭建实施计划

> **给后续执行者：**本计划用于搭建 Chain-AskData 自然语言取数 MVP 的第一版工程骨架。执行时按任务逐项推进，每一步都要可运行、可测试、可回滚。

**目标：**创建一个可运行的 Chain-AskData 项目骨架，支持输入自然语言问题后返回 QueryPlan、SQL、口径说明和校验结果。

**架构：**首版采用 FastAPI + 简单 Web 页面。后端先用确定性规则跑通链路，模块边界按 AskData-lite 拆分，后续再接入 DeepSeek、ChromaDB 和更完整的指标资产。

**技术栈：**Python 3.14、FastAPI、Pydantic、unittest、原生 HTML/CSS/JS。

---

## 1. 文件结构

- `app/main.py`：FastAPI 应用入口。
- `app/api/routes.py`：`/api/health` 和 `/api/query` 接口。
- `app/core/config.py`：环境变量配置。
- `app/models/query.py`：请求、响应、QueryPlan 数据模型。
- `app/metric_registry/registry.py`：MVP 指标注册表。
- `app/schema_retrieval/retriever.py`：Schema 检索接口占位。
- `app/query_planner/planner.py`：自然语言到 QueryPlan 的规划器。
- `app/sql_generator/generator.py`：根据 QueryPlan 生成 SQL。
- `app/sql_validator/validator.py`：SQL 安全与口径校验。
- `app/answer/composer.py`：组装最终响应。
- `app/web/routes.py`：Web 页面路由。
- `templates/index.html`：Codex 风格三栏页面。
- `static/styles.css`：页面样式。
- `static/app.js`：前端调用与渲染逻辑。
- `knowledge/examples/demo_queries.json`：Demo 问题资产。
- `tests/`：API、流水线、Validator 测试。

## 2. 任务拆分

### 任务 1：仓库基础文件

**文件：**
- 新建：`README.md`
- 新建：`.gitignore`
- 新建：`.env.example`
- 新建：`requirements.txt`
- 新建：`pyproject.toml`

**步骤：**
- [ ] 写入中文 README，说明项目定位、运行方式、目录结构。
- [ ] 写入 `.env.example`，只放变量名，不放真实密钥。
- [ ] 写入依赖声明。

### 任务 2：API 与数据模型

**文件：**
- 新建：`app/main.py`
- 新建：`app/api/routes.py`
- 新建：`app/core/config.py`
- 新建：`app/models/query.py`
- 新建：各包的 `__init__.py`
- 测试：`tests/test_api.py`

**步骤：**
- [ ] 先写接口测试，验证健康检查和查询接口响应结构。
- [ ] 运行测试，确认因应用代码缺失而失败。
- [ ] 实现 FastAPI 路由和 Pydantic 模型。
- [ ] 再次运行测试，确认通过。

### 任务 3：QueryPlan、SQL 生成与校验

**文件：**
- 新建：`app/metric_registry/registry.py`
- 新建：`app/schema_retrieval/retriever.py`
- 新建：`app/query_planner/planner.py`
- 新建：`app/sql_generator/generator.py`
- 新建：`app/sql_validator/validator.py`
- 新建：`app/answer/composer.py`
- 测试：`tests/test_validator.py`
- 测试：`tests/test_query_pipeline.py`

**步骤：**
- [ ] 先写 Validator 测试，覆盖只读 SQL、`dp`、`ORDER BY LIMIT`。
- [ ] 先写流水线测试，覆盖“最近30天各门店核销收入 TOP10”。
- [ ] 运行测试，确认失败。
- [ ] 实现最小可用的指标注册、规划、SQL 生成和校验。
- [ ] 再次运行测试，确认通过。

### 任务 4：Web 页面与 Demo 资产

**文件：**
- 新建：`app/web/routes.py`
- 新建：`templates/index.html`
- 新建：`static/styles.css`
- 新建：`static/app.js`
- 新建：`knowledge/examples/demo_queries.json`

**步骤：**
- [ ] 写入 Codex 风格页面：左侧输入，中间 QueryPlan，右侧 SQL。
- [ ] 写入 13 条 Demo 问题。
- [ ] 确认应用可以导入并启动。

### 任务 5：最终验证

**命令：**
- `python -m unittest discover -s tests -v`
- `python -m compileall app`
- `git status --short`

**步骤：**
- [ ] 确认测试通过。
- [ ] 确认 Python 文件可编译。
- [ ] 汇总本次创建的文件和下一步建议。
