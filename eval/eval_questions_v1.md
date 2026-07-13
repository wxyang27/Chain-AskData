# Chain-AskData 评估问题集 — 泛化能力测试（10 题）
# 生成时间：2026-07-13 · 更新时间：2026-07-13
# 设计目标：覆盖意图识别 / 业务域混淆 / 指标口径 / SQL 结构 / 安全兜底 五类错误
# 与 13 条 Demo 主问题不重复，作为 46 条黄金集后的泛化补充集
# 验收标准：硬验收 8/10，探索验收 2/10

| id | 问题 | 期望类型 | 难度 | 验收 | 必须命中 | 禁止出现 | 口径备注 |
|---|---|---|---|---|---|---|---|
| GEN_001 | 核销收入和核销GMV有什么不同？ | caliber_explain | easy | 硬 | exe_income, exe_amount, 核销收入不等于核销GMV, exe_income 是实收 / exe_amount 含赠送 | 生成 SELECT, 生成 SQL, SUM(exe_income), SUM(exe_amount) | 两道口径解释题的第一道：区分两个最容易被混用的金额字段。只要生成了 SQL 就说明意图分类没拦住。 |
| GEN_002 | 怎么看一个品项的大单品品项渗透率？ | caliber_explain | medium | 硬 | standard_name, customer_id, COUNT(DISTINCT customer_id), 总核销人数, 品项核销人数, NULLIF | product_name =, 渗透率不是用 product_id | 用提问式口径解释测试——用户不直接问"公式是什么"，而是问"怎么算"，系统要能识别出这是口径问题。另需验证 understanding of standard_name vs product_name distinction。 |
| GEN_003 | 最近7天大师团核销收入和新客核销人次占比 | nl2sql | hard | 硬 | revenue_category = '大师团', exe_income, is_new = 1, executed_date, is_valid = 1, COUNT(DISTINCT verify_date_id) | is_master = 1, channel_type, income_type, pay_date | 三雷合一：①大师团用 revenue_category 而非 is_master；②时间不是默认30天而是7天；③新客核销人次占比 = 新客核销人次/总核销人次。 |
| GEN_004 | 本周新客支付人数和支付客单价 | nl2sql | hard | 硬 | uid, COUNT(DISTINCT uid), SUM(pay_gmv), CONCAT(uid,pay_date), is_pay_new = 1, is_paydate_cash = 0, pay_date | customer_id, is_new = 1, exe_income, executed_date | 支付域全套口径集中测试：①新客=is_pay_new 不是 is_new；②人数=COUNT(DISTINCT uid)；③客单价分母=CONCAT(uid,pay_date)。去掉了"私域"，避免支付表无 cx_first_channel 导致的模糊验收。 |
| GEN_005 | 截至昨天各城市待核销服务点排行TOP5 | nl2sql | medium | 硬 | left_num > 0, city_name, SUM(left_num), SUM(left_gmv), 订单表, dp | is_valid = 1, executed_date BETWEEN, 核销表 | 待核销域集中测试：①必须用订单表而非核销表；②left_num > 0 而非 is_valid = 1；③城市维度通过门店维表 JOIN 获取；④待核销是存量快照不加业务日期区间。 |
| GEN_006 | 最近90天大单品的核销客单价和新客核销客单价分别是多少 | nl2sql | medium | 硬 | revenue_category = '大单品', exe_income, exe_income / COUNT(DISTINCT verify_date_id), is_new = 1 / is_new = 0, is_valid = 1, dp, executed_date | is_master, product_id, income_type, uid | 同一品类下新老客客单价拆分的经典经营问题：①90天需要建日期区间；②同时输出总计+新客+老客两个客单价；③验证 revenue_category 不是 income_type。 |
| GEN_007 | 昨天哪些门店出现了超过20%的0元核销？ | nl2sql | hard | 硬 | sy_hospital_name, exe_income = 0, COUNT(DISTINCT main_order_id), 0元单占比, tenant_id, executed_date, is_valid = 1, HAVING 或子查询 | pay_gmv = 0, COUNT(*), is_paydate_cash = 0 | 需要分组计算 0 元占比的聚合问题：①0元判定用 exe_income = 0；②分母是总订单数去重(主订单)；③>20% 需用 HAVING；④只取昨天，不要默认 30 天。 |
| GEN_008 | 怎么知道一个用户是不是连锁的L3以上会员 | schema_explain | easy | 探索 | membership_level, dm_opt_qy_user_summary_info_all_d, dim_user_qy_crm_customer_info_all_d, crm_customer_id | 生成 SELECT, 生成 SQL, FROM soyoung_dw, SUM, COUNT | **[探索]** 用户画像类 schema_explain：会员等级字段在用户汇总表和 CRM 维表中均可取。当前知识库 membership_level 检索可能不稳定，本条不放入硬验收，仅观察 schema_explain 在非核心域的表现。 |
| GEN_009 | 帮我分析为什么上周核销收入比上上周下降了 | unknown | easy | 硬 | 不生成 SQL, 暂不支持诊断/归因, 说明本系统只做取数不做事后分析 | SELECT, SUM(exe_income), executed_date | 归因类兜底拒答：用户要的是"为什么下降"而非"数据是多少"。系统必须识别为诊断意图而非取数。如果生成了两段时间的核销收入 SQL 就是误判。 |
| GEN_010 | 最近30天全连锁各品类的核销收入占比 | nl2sql | medium | 硬 | revenue_category, exe_income, SUM(exe_income), is_valid = 1, executed_date, dp | income_type, is_master, pay_gmv, product_id | 品类占比题：①revenue_category 分组；②占比 = 单品类核销收入 / 总收入；③验证不会用了 income_type 或 is_master；④窗口函数或子查询双段聚合。 |
