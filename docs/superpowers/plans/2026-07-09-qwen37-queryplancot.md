# Qwen3.7-Plus QueryPlanCoT Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 使用阿里云百炼 `qwen3.7-plus` 生成并校验 QueryPlanCoT 四元组，在失败时可靠回退规则结果，并在 Web 页面展示完整状态。

**Architecture:** 保留现有三级索引、SchemaGraph 和模板 SQL 主链路。Qwen 只接收用户问题与局部 SchemaGraph，返回结构化四元组；本地校验器负责验证数据库、表、字段和关系是否真实存在，校验失败最多修复一次，仍失败则采用规则 QueryPlanCoT。

**Tech Stack:** Python 3.14、FastAPI、Pydantic、python-dotenv、阿里云百炼 OpenAI 兼容 API、原生 JavaScript、pytest

---

### Task 1: 加载百炼环境配置

**Files:**
- Modify: `app/core/config.py`
- Modify: `requirements.txt`
- Modify: `pyproject.toml`
- Modify: `.env.example`
- Test: `tests/test_config.py`

- [ ] **Step 1: 编写失败测试**

在临时目录写入 `.env`，重新加载配置模块，断言 `LLM_ENABLED=true`、`LLM_COT_MODEL=qwen3.7-plus` 被读取，且环境变量优先于文件值。

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_config.py -v`

Expected: FAIL，当前配置模块不会读取 `.env`。

- [ ] **Step 3: 实现最小配置加载**

在创建 `Settings` 前调用 `load_dotenv()`；将示例模型更新为 `qwen3.7-plus`，保留 `LLM_ENABLED=false` 的安全默认值。

- [ ] **Step 4: 验证配置测试**

Run: `pytest tests/test_config.py -v`

Expected: PASS。

### Task 2: 校验 Qwen 四元组

**Files:**
- Create: `app/llm/query_plan_cot_validator.py`
- Modify: `app/llm/query_plan_cot_generator.py`
- Modify: `app/llm/prompts.py`
- Test: `tests/test_query_plan_cot_validator.py`
- Test: `tests/test_llm_query_plan_cot.py`

- [ ] **Step 1: 编写字段、关系和输出目标失败测试**

覆盖合法四元组、不存在字段、虚构关联、空输出目标和错误数据库。

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_query_plan_cot_validator.py -v`

Expected: FAIL，校验器尚不存在。

- [ ] **Step 3: 实现 SchemaGraph 约束校验器**

解析 `table.field` 和 `table.field <-> table.field`，只允许 SchemaGraph 中存在的对象；返回结构化错误列表，不抛出业务异常。

- [ ] **Step 4: 修复中文 Prompt 并接入校验**

Prompt 强制 JSON 四元组、禁止 SQL 和虚构对象。生成结果通过 Pydantic 解析后必须经过本地校验；失败时返回规则四元组和明确原因。

- [ ] **Step 5: 验证 LLM 单测**

Run: `pytest tests/test_query_plan_cot_validator.py tests/test_llm_query_plan_cot.py -v`

Expected: PASS。

### Task 3: 补全可观测状态

**Files:**
- Modify: `app/models/query.py`
- Modify: `app/query_planner/planner.py`
- Modify: `static/app.js`
- Modify: `templates/index.html`
- Test: `tests/test_llm_query_plan_cot.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: 编写状态字段失败测试**

断言 API 返回 `llm_enabled`、`llm_adopted`、`llm_model`、`llm_validation_passed`、`llm_latency_ms`、`llm_repair_count` 和 `llm_fallback_reason`。

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_api.py tests/test_llm_query_plan_cot.py -v`

Expected: FAIL，新增状态字段不存在。

- [ ] **Step 3: 实现状态采集与页面展示**

记录调用耗时和校验结果；前端用固定标签展示状态，HTTP 或 JSON 异常时显示错误，不再永久停留在“等待生成”。

- [ ] **Step 4: 增加静态资源版本参数**

为 `app.js` 增加版本查询参数，避免浏览器继续使用旧脚本。

- [ ] **Step 5: 验证 API 与前端相关测试**

Run: `pytest tests/test_api.py tests/test_llm_query_plan_cot.py -v`

Expected: PASS。

### Task 4: 全链路验证与服务重启

**Files:**
- Verify only

- [ ] **Step 1: 运行全量测试**

Run: `pytest -q`

Expected: 全部通过，仅允许已知 ChromaDB/Python 3.14 弃用警告。

- [ ] **Step 2: 停止旧 Uvicorn 进程**

确认 PID 对应 `Chain-AskData` 的 Uvicorn 后停止进程，不影响其他 Python 服务。

- [ ] **Step 3: 启动新服务**

Run: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`

Expected: `http://127.0.0.1:8000/` 可访问。

- [ ] **Step 4: 执行真实百炼冒烟测试**

问题：`本周私域新客核销收入是多少？`

Expected: 页面显示 `qwen3.7-plus`、LLM 已启用、四元组校验结果、SchemaGraph；SQL 仍由模板生成。

