# Chain-AskData 黄金评测集 v1.2 · 使用说明

> 创建时间：2026-07-10
> 更新时间：2026-07-13（v1.3·基线固化：46/46 + 10/10 全量通过）
> 评测集文件：`eval/golden_eval_set.json`
> 评测脚本：`eval/run_eval.py`
> 总样例数：46 条

---

## 一、为什么需要评测集

13 个 Demo 是**能力展示**，不是**准确率评测**：

| 问题 | Demo | 评测集 |
|---|---|---|
| 数量 | 13 条 | 36 条 |
| 问法 | 标准化 | 含口语/同义/省略/歧义变体 |
| 覆盖 | 只测"能做什么" | 测"各种变体下是否还能做对" |
| 标注 | 有 question + SQL 模板 | 有结构化标准答案（intent/metrics/tables/fields/filters/patterns/caliber） |
| 归因 | 无法定位错误来源 | 可分层归因（检索/CoT/SQL/口径） |

**Demo 是起点，评测集是验收线。**

---

## 二、评测集结构

### 2.1 meta 元信息

```json
{
  "pass_criteria": "SQL 结构对 + 口径解释对",
  "target_user": "经管中心业务人员",
  "metric_id_standard": "评测指标以 core_metrics.yaml canonical 为准（如 execution_income），不以飞书 A 编码为准",
  "difficulty_def": { "easy / medium / hard": "..." },
  "category_dist": { "standard": 13, "synonym_rewrite": 8, ... },
  "difficulty_dist": { "easy": 10, "medium": 15, "hard": 11 }
}
```

### 2.2 单条样例字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 评测编号 EVAL_001-036 |
| `question` | string | 用户自然语言问题 |
| `category` | enum | standard / synonym_rewrite / caliber_confusion / composite / reject_boundary / schema_explain / caliber_explain |
| `difficulty` | enum | easy / medium / hard |
| `source_demo_id` | string\|null | 来自 13 Demo 的 case_id，新增变体为 null |
| `expected_intent` | enum | nl2sql / schema_explain / caliber_explain / unknown |
| `expected_metrics` | string[] | 应识别的指标 ID（**canonical**，非飞书 A 编码） |
| `expected_tables` | string[] | 应使用的表（含 soyoung_dw 前缀） |
| `expected_fields` | string[] | 应使用的字段 |
| `expected_dimensions` | string[] | 应分组的维度字段 |
| `expected_filters` | string[] | 关键过滤条件（结构化，非完整 SQL） |
| `expected_sql_must_contain` | string[] | SQL 里**必须**出现的关键词/表达式 |
| `expected_sql_any_of` | string[][] | 多组可接受写法，**任一**匹配即通过（如 LIKE vs REGEXP） |
| `forbidden_sql_patterns` | string[] | SQL 里**不该**出现的字段/错误口径 |
| `expected_caliber` | object | 口径卡片：definition + must_filters + known_risks |
| `evaluation_focus` | string[] | 本条主要测试的能力点 |
| `notes` | string | 标注说明 |

### 2.3 evaluation_focus 可选值

| 值 | 含义 |
|---|---|
| `intent_routing` | 意图路由是否正确 |
| `schema_retrieval` | Schema 检索是否命中正确表/字段 |
| `query_plan_cot` | LLM CoT 四元组规划是否正确 |
| `sql_generation` | SQL 生成是否正确 |
| `sql_safety` | 安全门禁是否生效 |
| `caliber` | 口径是否准确 |
| `reject_boundary` | 拒答边界是否守住 |
| `synonym_mapping` | 同义词映射是否正确 |

---

## 三、7 类样例设计

### 3.1 标准样例（13 条）— 保证已有能力不退化

直接来自 13 个 Demo 原问，`source_demo_id` 记录对应 case_id。

| ID | 来源 | 问题摘要 | 难度 |
|---|---|---|---|
| EVAL_001 | Q001 | 昨天核销5指标汇总 | easy |
| EVAL_002 | Q002 | 30天门店核销收入TOP10 | medium |
| EVAL_003 | Q003 | 本周私域新客核销收入 | easy |
| EVAL_004 | Q004 | 30天渠道核销收入/人次/客单价对比 | medium |
| EVAL_005 | Q005 | 30天新老客核销收入/人次/客单价 | medium |
| EVAL_006 | Q006 | 30天品类核销收入对比 | medium |
| EVAL_007 | Q007 | 30天品项核销收入TOP20 | medium |
| EVAL_008 | Q008 | 90天奇迹胶原渗透率 | hard |
| EVAL_009 | Q009 | 30天0元单数量和核销人数 | medium |
| EVAL_010 | Q010 | 门店待核销金额TOP10 | hard |
| EVAL_011 | Q011 | 30天新客支付GMV/人数/客单价 | medium |
| EVAL_012 | Q012 | 60天支付后30日核销率 | hard |
| EVAL_013 | Q013 | 30天升单人数/人次/收入 | medium |

### 3.2 同义改写（8 条）— 测语义灵活性

| ID | 改写自 | 同义映射 | 难度 |
|---|---|---|---|
| EVAL_014 | Q001 | "核销了多少钱"→核销收入 | easy |
| EVAL_015 | Q002 | "消耗金额"→核销收入，"近一个月"→30天 | medium |
| EVAL_016 | Q003 | "成交后收入"→核销收入，"这周"→本周 | easy |
| EVAL_017 | Q005 | "业绩"→核销收入，省略人次/客单价 | medium |
| EVAL_018 | Q007 | "核销金额"→核销收入（非GMV），"前20"→LIMIT 20 | medium |
| EVAL_019 | Q010 | "机构"→门店，"没核销的金额"→待核销 | hard |
| EVAL_020 | Q011 | "付了多少"→支付GMV，"人均多少"→支付客单价 | medium |
| EVAL_021 | Q009 | "有多少笔"→订单数，"涉及多少客人"→核销人数 | medium |

### 3.3 口径易混（5 条）— 测业务准确率

| ID | 易混点 | 测试目标 | 难度 |
|---|---|---|---|
| EVAL_022 | 核销收入 vs 支付GMV | 双域双表双日期过滤不混淆 | hard |
| EVAL_023 | 核销人数 vs 核销人次 | customer_id vs verify_date_id | hard |
| EVAL_024 | 核销日 vs 支付日 | executed_date vs pay_date | hard |
| EVAL_025 | 核销收入 vs 核销GMV | exe_income vs exe_amount | hard |
| EVAL_026 | 待核销库存口径 | 不加 pay_date 截断 | hard |

### 3.4 组合问题（2 条）— 测模板外组合能力

| ID | 组合维度 | 测试目标 | 难度 |
|---|---|---|---|
| EVAL_027 | 渠道 × 新客 × TOPN | 无模板时LLM自由生成 | hard |
| EVAL_028 | 门店 × 新老客 对比 | JOIN + 双维度 GROUP BY | hard |

### 3.5 拒答边界（4 条）— 测系统不乱生成 SQL

| ID | 来源 | 问题 | 期望意图 | 难度 |
|---|---|---|---|---|
| EVAL_029 | 飞书表小鹿真实越界 | 天气对门店收入影响 | unknown | easy |
| EVAL_030 | 预测类越界 | 预测下月收入 | unknown | easy |
| EVAL_035 | 业务诊断越界 | 为什么昨天收入下降 | unknown | easy |
| EVAL_036 | 业务诊断越界 | 帮我分析哪个门店有问题 | unknown | easy |

> ⚠ EVAL_030/035/036 命中"收入"/"门店"等业务词，可能被 IntentRouter 误判为 nl2sql，是**路由缺陷暴露样例**。

### 3.6 Schema 解释（2 条）— 测字段知识检索 [v1.1 新增]

| ID | 问题 | 期望意图 | 测试目标 | 难度 |
|---|---|---|---|---|
| EVAL_031 | 核销人数应该用哪个字段？ | schema_explain | customer_id 字段知识 | easy |
| EVAL_032 | 门店名称用哪个字段？ | schema_explain | sy_hospital_name 主推字段 | easy |

### 3.7 口径解释（2 条）— 测口径定义解释 [v1.1 新增]

| ID | 问题 | 期望意图 | 测试目标 | 难度 |
|---|---|---|---|---|
| EVAL_033 | 核销收入和支付GMV有什么区别？ | caliber_explain | 双域口径对比解释 | medium |
| EVAL_034 | 核销客单价的分母是什么？ | caliber_explain | 客单价分母（人次vs人数） | medium |

---

## 四、难度分布

| 难度 | 数量 | 占比 | 典型特征 |
|---|---|---|---|
| easy | 10 | 22% | 单表标准问法 / 直接拒答 / 纯解释类 |
| medium | 18 | 39% | JOIN或同义改写或单表多指标+维度 / 口径解释需跨域对比 / MTD单维度 |
| hard | 18 | 39% | CTE/TOPN/对比+歧义口径/模板外组合/多维度+MTD组合 |

---

## 五、Critical Rules（v1.2 新增）

7 条不可违反的硬规则，每条 hard case 标注了 `critical_rules` 字段，runner 自动检测并校验：

| 规则 ID | 规则 | 检查逻辑 |
|---|---|---|
| CR001_dp | dp 必须等于 DATE_SUB(CURRENT_DATE(),1) | SQL 含 `dp=DATE_SUB(CURRENT_DATE()`，禁止 `dp BETWEEN` / `dp >=` 区间 |
| CR002_mtd | "本月"必须用自然月 MTD | SQL 含 DATETRUNC / DATE_FORMAT yyyy-MM-01 / SUBSTR+01，禁止用最近30天替代 |
| CR003_city | 城市必须用 city_name | SQL 含 `city_name`，禁止裸 `city` |
| CR004_store | 门店必须用 sy_hospital_name | SQL 含 `sy_hospital_name` 或 `tenant_alias_name`，禁止 `hospital_name` 无前缀 |
| CR005_item | 品项必须用 standard_name | SQL 含 `standard_name`，禁止 `product_name` |
| CR006_channel | 渠道必须用 cx_first_channel | SQL 含 `cx_first_channel`，禁止裸 `channel_type` |
| CR007_newold | 核销域用 is_new，支付域用 is_pay_new | 按问题域检测，不可混用 |

### 质量门槛

```text
overall >= 80%      # 全量通过率
hard >= 75%         # hard 难度通过率
critical_rule >= 95%  # critical rule 通过率
```

三门全过才算"稳定可测地能用"。

---

## 六、v1.2 新增 hard case（10 条）

| ID | 问题 | Critical Rules | 难度 |
|---|---|---|---|
| EVAL_037 | 本月核销收入 | CR001+CR002 | medium |
| EVAL_038 | 本月各城市核销收入 | CR001+CR002+CR003 | hard |
| EVAL_039 | 本月北京地区奇迹胶原核销收入 | CR001+CR002+CR003+CR005 | hard |
| EVAL_040 | 本月各门店新老客核销收入 | CR001+CR002+CR004+CR007 | hard |
| EVAL_041 | 本月各渠道新客核销收入 | CR001+CR002+CR006+CR007 | hard |
| EVAL_042 | 最近30天北京门店核销收入 | CR001+CR003+CR004 | hard |
| EVAL_043 | 本月各品项核销收入TOP10 | CR001+CR002+CR005 | hard |
| EVAL_044 | 本月私域核销收入 | CR001+CR002+CR006 | medium |
| EVAL_045 | 本月新客支付GMV | CR001+CR002+CR007 | hard |
| EVAL_046 | 昨天各城市核销收入 | CR001+CR003 | medium |

---

## 七、版本修正记录

| 修正项 | v1.0 | v1.1 | v1.2 |
|---|---|---|---|
| 门店名字段 | `tenant_alias_name` | `sy_hospital_name` + any_of | 同 v1.1 |
| SQL pattern 结构 | 单一列表 | must_contain + any_of + forbidden 三段式 | 同 v1.1 |
| 品项匹配写法 | 仅 LIKE | LIKE 或 REGEXP 均可 | 同 v1.1 |
| 评测焦点 | 无 | evaluation_focus 字段 | 同 v1.1 |
| 意图覆盖 | nl2sql + unknown | + schema_explain + caliber_explain | 同 v1.1 |
| 拒答边界 | 2 条 | 4 条 | 4 条 |
| 指标 ID 标准 | 未声明 | canonical 声明 | 同 v1.1 |
| Critical Rules | 无 | 无 | **7 条 CR001-CR007 + 自动校验** |
| 质量门槛 | 无 | 无 | **overall 80% / hard 75% / critical 95%** |
| MTD 测试 | 无 | 无 | **10 条 hard case** |
| 总数 | 30 | 36 | **46** |

---

## 六、评测执行流程

### 6.1 跑评测（每次改检索/Prompt/SchemaGraph/SQL 修复后）

```bash
# 确保 Chain-AskData 服务已启动
python eval/run_eval.py --api http://localhost:8000 --output eval/eval_result_20260710.json
```

### 6.2 评分规则

| 检查项 | 权重 | 判定 |
|---|---|---|
| intent 正确 | 必须通过 | 错则整条 fail |
| metrics 命中 | 30% | 缺/多指标扣分 |
| tables 正确 | 20% | 表选错扣分 |
| fields 正确 | 20% | 字段错扣分 |
| filters 正确 | 15% | 关键过滤缺失扣分 |
| must_contain 全部出现 | 必须通过 | 缺一即扣分 |
| any_of 任一命中 | 通过 | 全不命中才扣分 |
| forbidden 未触发 | 必须通过 | 触发即整条 fail |
| caliber 准确 | 15% | 口径卡片定义/风险描述偏差扣分 |

### 6.3 错误归因分层

当一条 fail 时，按 `evaluation_focus` + 以下顺序定位错误来源：

```
fail
 ├─ intent 错 → IntentRouter 问题（检索/路由）          [intent_routing]
 ├─ metrics 错 → QueryPlanCoT 问题（LLM 规划）           [query_plan_cot]
 ├─ tables 错 → SchemaGraph 检索问题（知识库/索引）       [schema_retrieval]
 ├─ fields 错 → SchemaGraph 字段补全问题（enricher）      [schema_retrieval]
 ├─ filters 错 → SQL 生成问题（模板/LLM）                [sql_generation]
 ├─ must_contain 缺失 → SQL 生成问题（模板/LLM）          [sql_generation]
 ├─ forbidden 触发 → 口径混淆（安全门禁未拦住）            [caliber] [sql_safety]
 └─ caliber 错 → 口径卡片组装问题（AnswerComposer）       [caliber]
```

---

## 七、与 13 Demo 的关系

```
13 个 Demo 问题（能力展示）
  ↓ 扩写 / 改写 / 加边界 / 加反例
36 条评测集（准确率验收）

13 条标准样例（Demo 原问，保证不退化）
 + 8 条同义改写（口语化变体）
 + 5 条口径易混（业务准确率）
 + 9 条组合问题（模板外能力，含 10 条 critical rule hard case）
 + 4 条拒答边界（不乱生成 SQL）
 + 2 条 schema_explain（字段知识检索）
 + 2 条 caliber_explain（口径定义解释）
 = 46 条黄金评测集
```

---

## 八、泛化补充集（v1 extra）

### 8.1 定位

`eval/golden_eval_set_v1_extra.json` 是**泛化补充集**，不替代主黄金集：

| 维度 | 主黄金集 | 泛化补充集 |
|------|---------|-----------|
| 文件 | `golden_eval_set.json` | `golden_eval_set_v1_extra.json` |
| 数量 | 46 条 | 10 条 |
| 定位 | 能力验收基线 | 泛化边界验证 |
| 来源 | 13 Demo 扩写 | 模板外口语/自由组合 |
| 评测时机 | 每次改动必跑 | 重大版本后验证 |

### 8.2 v1 基线结果

```
主黄金集: 46/46 (100%)
泛化补充集: 10/10 (100%)
```

评测结果文件：
- `eval/eval_result_after_step2_gold46.json`
- `eval/eval_result_v1_extra_after_step2.json`

---

## 九、后续扩展建议

| 阶段 | 扩展方向 | 目标数量 |
|---|---|---|
| v1.1（当前） | 36 条黄金集 | 36 |
| v1.2 | 补充飞书表小鹿真实问题变体 | 50 |
| v1.3 | 加入趋势图表类问题（Phase 6 后） | 80 |
| v2.0 | 加入执行结果数值校验（Phase 6 后） | 100+ |

---

## 九、数据来源

1. **13 Demo**（项目内 `knowledge/examples/demo_queries.json`）→ 标准样例 + 改写基底
2. **飞书表小鹿智能体评测**（337 条记录，提取 30 条有效问题）→ 同义改写参考 + 拒答边界
3. **chain-nl-query skill 口径字典**（58 高频指标 + 132 衍生指标 + 口语同义词表）→ 口径易混 + expected_caliber
4. **工程资产对齐**（`app/schema_graph/enricher.py` 依赖矩阵）→ 字段名以 `sy_hospital_name` 为准
