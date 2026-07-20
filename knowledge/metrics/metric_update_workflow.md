# 指标资产更新流程

本文档用于约束 Chain-AskData 中指标的新增、更新、废弃和评测发布流程。

## 0. 为什么要做资产治理

这里的资产治理不是额外工作，而是“新增指标更新流程”的标准承载方式。

如果只把新指标写进一段 prompt，短期能回答，长期会有三个风险：

1. 口径变了，但 SQL、解释和评测没有同步变。
2. 模型知道“时间进度达成率”这个词，但不知道目标表、层级筛选和日期规则。
3. 后续同类指标扩展时，每次都重新靠人工描述，无法复用。

所以新增指标时，要把它沉淀为一条指标资产：定义、公式、来源表、过滤条件、风险、评测用例一起更新。

## 0.1 样板：新增“奇迹胶原本月核销收入时间进度达成率”

业务口径：

```text
时间进度达成率 =
(本月截至昨天实际核销收入 / 本月目标收入) / (本月截至昨天天数 / 本月总天数)
```

示例：

```text
(33762 / 48263) / (19 / 31) = 114.14%
```

实际值资产：

- 指标：核销收入
- 来源表：`soyoung_dw.dm_opt_qy_user_execution_record_all_d`
- 金额字段：`exe_income`
- 日期字段：`executed_date`
- 品项字段：`standard_name`
- 必要过滤：`dp = DATE_SUB(CURRENT_DATE(), 1)`、`is_valid = 1`、`standard_name = '奇迹胶原'`
- 时间范围：本月 1 日至昨天

目标值资产：

- 来源表：`soyoung_dw.dim_channel_month_income_target`
- 目标字段：`target_absolute_value`
- 月份字段：`month`
- 必要过滤：`first_level_hierarchy = '货'`、`third_level_hierarchy = '奇迹胶原'`、`fourth_level_hierarchy = '整体'`、`target_type = '收入'`

推荐 SQL 样板：

```sql
WITH actual_income AS (
  SELECT  SUM(exe_income) AS actual_exe_income
  FROM    soyoung_dw.dm_opt_qy_user_execution_record_all_d
  WHERE   dp = DATE_SUB(CURRENT_DATE(), 1)
  AND     is_valid = 1
  AND     standard_name = '奇迹胶原'
  AND     executed_date >= DATE_FORMAT(CAST(CURRENT_DATE() AS TIMESTAMP), 'yyyy-MM-01')
  AND     executed_date <= DATE_SUB(CURRENT_DATE(), 1)
),
target_income AS (
  SELECT  target_absolute_value AS target_exe_income
  FROM    soyoung_dw.dim_channel_month_income_target
  WHERE   month = DATE_FORMAT(CAST(CURRENT_DATE() AS TIMESTAMP), 'yyyy-MM')
  AND     first_level_hierarchy = '货'
  AND     third_level_hierarchy = '奇迹胶原'
  AND     fourth_level_hierarchy = '整体'
  AND     target_type = '收入'
),
date_progress AS (
  SELECT  DATEDIFF(
            DATE_SUB(CURRENT_DATE(), 1),
            TO_DATE(DATE_FORMAT(CAST(CURRENT_DATE() AS TIMESTAMP), 'yyyy-MM-01'))
          ) + 1 AS elapsed_days,
          DAY(LAST_DAY(CURRENT_DATE())) AS month_days
)
SELECT  a.actual_exe_income,
        t.target_exe_income,
        d.elapsed_days,
        d.month_days,
        a.actual_exe_income / NULLIF(t.target_exe_income, 0) AS target_completion_rate,
        d.elapsed_days / NULLIF(d.month_days, 0) AS time_progress_rate,
        (a.actual_exe_income / NULLIF(t.target_exe_income, 0))
        / NULLIF(d.elapsed_days / NULLIF(d.month_days, 0), 0) AS time_progress_achievement_rate
FROM    actual_income a
CROSS JOIN target_income t
CROSS JOIN date_progress d;
```

这条指标已经落入 `knowledge/metrics/metric_assets.yaml`，canonical 为：

```text
miracle_collagen_execution_income_time_progress_rate
```

## 1. 核心原则

1. 先治理资产，再扩充查询能力。
2. 能 SQL 的指标必须有表、字段、日期字段、过滤条件和关键规则。
3. 不能 SQL 的指标也要明确支持状态，优先做到可解释、可拒答。
4. 每次口径变化必须同步更新评测集。
5. P0/P1 指标不得只靠 prompt 记忆，必须进入 `metric_assets.yaml`。

## 2. 支持状态

| 状态 | 处理方式 |
|---|---|
| `sql_supported` | 可进入 SQL 生成、模板、示例查询和 golden eval。 |
| `explain_only` | 只回答定义、公式、依赖和暂不支持 SQL 的原因。 |
| `exploratory` | 可进入探索集，用于验证关联键、字段、目标来源和时间窗。 |
| `unsupported` | 明确拒答或转人工/数据口径确认。 |

## 3. 新增指标流程

### Step 1：需求登记

记录以下内容：

- 业务问题原文。
- 指标中文名和常见问法。
- 指标用途：看总盘、看门店、看品项、看渠道、看进度、看利润。
- 预期支持范围：SQL 查询、口径解释、趋势明细、TOP 排名、占比。

### Step 2：判断支持状态

判断规则：

- 有明确表字段、时间字段和过滤条件：`sql_supported`。
- 有业务公式但缺目标表、目标层级或映射关系：`explain_only`。
- 关联键、数据源、归因口径需要验证：`exploratory`。
- 涉及敏感数据、删除数据、预测归因到员工等：`unsupported`。

### Step 3：补齐指标资产

在 `knowledge/metrics/metric_assets.yaml` 中补齐：

- `canonical`
- `display_name`
- `aliases`
- `priority`
- `metric_type`
- `business_domain`
- `support_status`
- `definition`
- `formula_sql`
- `source_tables`
- `date_field`
- `required_fields`
- `required_filters`
- `supported_dimensions`
- `forbidden_fields`
- `critical_rules`
- `known_risks`
- `capability_notes`
- `version`
- `eval_cases`

### Step 4：补评测用例

最低要求：

- 每个新增指标至少 1 条口径解释类评测。
- 每个 `sql_supported` 指标至少 1 条 SQL 查询类评测。
- 每个 ratio 指标必须测分子、分母和除零处理。
- 每个易混指标必须测 forbidden 或边界解释。

建议用例类型：

- easy：问定义、字段、来源表。
- medium：固定时间 + 单指标聚合。
- hard：固定时间 + 多维切片 + 占比或 TOP。
- boundary：不能 SQL 时说明原因。

### Step 5：接入查询链路

SQL 支持指标需要同步检查：

- `app/cot_planning/intent_router.py` 是否能识别意图。
- `app/cot_planning/semantic_contract.py` 是否能抽取指标和维度。
- `app/sql_generation/template_generator.py` 是否已有稳定模板。
- `knowledge/examples/` 是否有相似示例。
- `eval/golden_eval_set_*.json` 是否覆盖关键规则。

### Step 6：回归评测

建议命令：

```powershell
python -m json.tool eval\metric_asset_eval.json > $null
python eval\run_schema_retrieval_eval.py
python eval\run_eval.py --eval-set eval\golden_eval_set_p0_v1.json
```

如果 HTTP 服务受阻，也可以使用当前项目已有的 direct eval 脚本方式，但结果文件必须保留在 `eval/` 目录。

### Step 7：发布与记录

发布前检查：

- 指标资产字段完整。
- 评测用例通过。
- P0/P1 critical rule 没有下降。
- 新指标支持状态与实际能力一致。
- 旧口径如需废弃，保留兼容说明。

## 4. 更新指标流程

当业务口径变更时，必须同步更新：

- `metric_assets.yaml` 中的定义、公式、字段和风险。
- SQL 模板或示例查询。
- 相关评测集的 expected fields / critical rules。
- 变更版本号。

版本建议：

- 只补别名、说明：patch，例如 `1.0.1`。
- 改公式或字段：minor，例如 `1.1.0`。
- 口径不兼容：major，例如 `2.0.0`。

## 5. 废弃指标流程

废弃指标不要直接删除，先改为：

```yaml
support_status: unsupported
deprecation:
  deprecated_at: "YYYY-MM-DD"
  replaced_by: new_metric_canonical
  reason: "业务口径废弃原因"
```

至少保留一个版本周期，避免历史评测和业务文档断链。

## 6. 当前 P1 指标扩充顺序

本阶段只推进时间进度达成率，不扩展 ROI、成本、毛利等其他指标。

### 6.1 样板指标

先完成：

- `miracle_collagen_execution_income_time_progress_rate`
- 中文名：奇迹胶原本月核销收入时间进度达成率
- 状态：`sql_supported`

验收内容：

- 能解释口径。
- 能说明实际值来源。
- 能说明目标值来源。
- 能说明时间进度为什么是截至昨天。
- 能基于示例值算出 114.14%。

### 6.2 同类复制

样板稳定后，再扩到其他品项。

复制规则：

- 只替换 `standard_name` 和目标表中的品项层级。
- 不改核销收入字段 `exe_income`。
- 不改实际日期字段 `executed_date`。
- 不改目标字段 `target_absolute_value`。
- 不改时间进度公式。

## 7. PR 检查清单

新增或更新指标时，提交前检查：

- [ ] 指标有唯一 canonical。
- [ ] 支持状态准确。
- [ ] SQL 支持指标有 source table、date field、formula、filters。
- [ ] ratio 指标有分子、分母和除零处理。
- [ ] 易混字段已写入 `forbidden_fields` 或 `known_risks`。
- [ ] 至少新增或更新 1 条评测用例。
- [ ] 评测结果未拉低 P0 基线。
- [ ] 文档说明与机器资产一致。

## 8. 常见变更示例

### 修改“新客”字段规则

如果业务确认核销新客字段变化，需要同步更新：

- `execution_income` 的 `known_risks`。
- `critical_rules.CR007_new_customer_field`。
- 涉及新客问题的 golden eval。
- semantic contract 的字段选择逻辑。

### 修改“时间进度达成率”的时间规则

如果业务将“截至昨天自然日进度”改为“营业日进度”，必须同步更新：

- `metric_assets.yaml` 中的 `time_progress_formula`。
- SQL 模板中的 `date_progress` CTE。
- `CR016_time_progress_as_of_yesterday` 或新增 critical rule。
- `METRIC_ASSET_018` 中的示例天数和预期结果。
