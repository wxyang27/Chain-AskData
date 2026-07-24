# AskData Agent 面试故事线

## 1. 一句话定位

我在数据智能部-数据架构组做数据仓库开发，服务对象主要是经管中心下的战略咨询、商业分析、经营分析等业务同事，目标用户规模大约 20-50 人。AskData Agent 是我围绕真实取数场景做的一个业务驱动型数据智能项目：把数仓里已经沉淀的指标口径、表结构、样例 SQL 和执行校验能力，封装成一条可解释、可评测、可回退的 Agentic Text2SQL Workflow。

一句话讲：

> 这个项目不是让大模型直接写 SQL，而是用 Plan-and-Execute + Reflection 的范式，把业务问题理解、schema 检索、语义层映射、查询规划、SQL 生成、安全校验、执行反馈和多轮记忆串成一个可控的问数 Agent。

业务目标是三件事：

1. 满足业务同事高频取数需求，缩短基础数据响应时长。
2. 帮业务团队建立自己的数据运营能力，减少所有需求都中心化压到数仓同学身上。
3. 消除跨部门指标歧义，保证核销收入、支付 GMV、新老客、渠道、品项等核心口径一致。

## 2. 60 秒开场话术

我做 AskData Agent 的背景是，数据架构组长期承接经管中心其他部门的经营取数需求。比如战略咨询、商业分析、经营分析同事会频繁问“最近 30 天各门店核销收入 TOP10”“本月华北大区支付金额”“最近 30 天私域、公域、老带新的核销收入、人次、客单价对比”等问题。

这些问题对业务同事来说是自然语言，但对数仓同学来说背后有很多隐含条件：应该用核销表还是支付表，日期应该用 `executed_date` 还是 `pay_date`，核销收入应该用 `exe_income`，支付 GMV 应该用 `pay_gmv`，城市和大区字段在维表里，分区还要带 `dp = yesterday`。如果只让大模型直接写 SQL，很容易出现字段幻觉、口径混淆、漏过滤或漏分组。

所以我先把项目定位成业务驱动，而不是模型驱动。我们每周和业务部门开指标评审会，把核心指标、衍生指标、确认口径、数据源和 SQL 口径沉淀到[【经营管理中心】数据字典](https://soyoung.feishu.cn/sheets/WQRbsbh0QhEfuPt6onHcGcHbnGh)，同时整理[数据小课堂 · 连锁数仓表地图](https://soyoung.feishu.cn/docx/CoWrdfPYioN3ZxxSWKbcG4EGnKf)，补充易混淆字段和表关系。基于这些知识资产，我搭建了 AskData Agent：用户在 CLI、Web 或飞书里提问后，系统先做短期记忆补全和语义层解析，再通过混合检索召回指标和 schema，生成 QueryPlanCoT 和 SQL，经过 Safety Gate、执行、结果校验和修复回退后返回结果。

目前项目已经跑通了从自然语言取数到 SQL 生成和飞书返回的端到端链路，并建立了评测体系。最近一次短期记忆 P0 评测 12 个 case、34 轮对话通过率 100%，P1 复杂追问 4 个 case、8 轮通过率 100%；LLM SQL 在 P0 前 10 条样本上的采纳率也从 60% 提升到 80%。我也清楚当前不足：还缺后训练、标准 MCP 路由协议和更完整的长期记忆，所以后续规划是补语义层、reflection、权限治理和反馈数据闭环。

## 3. 面试展开版

### 3.1 业务问题

可以用 STAR 法则讲。

**Situation：业务侧取数需求高频且分散。**
经管中心下战略咨询、商业分析、经营分析等团队经常需要看门店、品项、渠道、新老客、大区等经营数据。用户规模虽然不是几千人级产品，但 20-50 个高频业务用户已经足以形成持续的基础取数压力。

**Task：既要响应业务，又要保证口径一致。**
我的任务不是简单做一个 SQL 生成 demo，而是把数仓团队沉淀的指标知识和取数经验产品化，让业务同事能自助完成一部分标准取数，同时让数仓同学从重复 SQL 中释放出来。

**Action：先做指标治理，再做 Agent。**
我没有一开始就把问题丢给大模型，而是先和业务部门一起梳理指标字典、数仓表地图、易混淆字段、核心 SQL 样例和评测集。然后用 Agentic Workflow 把“用户问题 -> 语义理解 -> schema 召回 -> 计划生成 -> SQL 生成 -> 校验执行 -> 反馈修复”串起来。

**Result：形成可评测、可迭代的问数链路。**
项目已经支持高频经营问数、多轮短追问、模板 SQL 和 LLM SQL 双路径、MaxCompute 只读执行、飞书 CatData 机器人入口和评测闭环。它不只是能演示，而是能解释每一步为什么这么做、失败时在哪里失败、下一步怎么修。

### 3.2 业务资产

这个项目的壁垒不是 prompt，而是业务资产。

1. 指标字典
   每周和业务部门开指标评审会，把原子指标、衍生指标、业务定义、SQL 口径、数据源表、确认方沉淀到[【经营管理中心】数据字典](https://soyoung.feishu.cn/sheets/WQRbsbh0QhEfuPt6onHcGcHbnGh)。例如核销收入、核销 GMV、支付 GMV、支付人数、0 元单、待核销金额、支付后 30 日核销率等。

2. 数仓表地图
   通过[数据小课堂 · 连锁数仓表地图](https://soyoung.feishu.cn/docx/CoWrdfPYioN3ZxxSWKbcG4EGnKf)梳理 DIM、DWD、DWS、DM 分层，以及连锁经营分析优先使用哪些宽表、哪些字段来自维表、哪些 join key 必须保留。

3. 易混淆口径
   明确支付域和核销域的区别，人数和人次的区别，`tenant_id` 和门店维表的关系，`city_name`、`area_name`、`sy_hospital_name` 的字段归属。

4. 评测集
   把典型业务问题整理成 golden case，包括指标、维度、过滤、时间、SQL 关键约束和预期模板，用于评估准确率、采纳率、召回率和多轮记忆稳定性。

面试时可以强调：

> 大模型应用在数据场景里的核心不是“让模型更会说话”，而是让业务知识变成机器可消费、可校验、可评测的资产。

## 4. 技术链路

### 4.1 离线知识构建

离线层负责把业务文档、指标表、schema 文件和样例 SQL 变成可检索资产。

```text
飞书指标字典 / 数仓表地图 / YAML / Markdown / 样例 SQL
  -> 指标与字段标准化
  -> metric registry
  -> schema indexes
  -> table relations
  -> example query assets
  -> ChromaDB 向量库
  -> golden eval / memory eval
```

技术点可以拆成：

1. 用户意图和业务术语标准化
   将“支付金额、支付收入、收款、流水”统一映射到支付 GMV 语义簇，将“华北大区、华北地区、华北战区”统一映射到 `area_name`。

2. 三级索引
   为字段、指标、表关系构建关键词索引、向量索引和 rerank 文本索引，既保证精确命中，也保留语义召回能力。

3. 向量数据库
   使用 ChromaDB 存储 schema、metric、example chunks，Embedding 可以接 DashScope，也可以 fallback 到本地 HashEmbedding。

4. 评测资产
   离线维护 schema retrieval eval、golden SQL eval、memory follow-up eval，让每次 prompt、语义层或 SQL 规则调整都有回归保护。

### 4.2 在线问答链路

在线链路可以用一条主线讲：

```text
User Question
  -> Memory Resolution
  -> Semantic Layer
  -> Hybrid Retrieval
  -> Schema Graph
  -> QueryPlanCoT
  -> SQL Generation
  -> Safety Gate
  -> Execution
  -> Result Validation
  -> Repair / Fallback
  -> Feishu Card / API Response
```

1. Memory Resolution
   保存最近 3 轮结构化状态。用户说“那上海呢”“top3”“本周呢”“支付金额呢”时，不是简单拼接历史问题，而是先解析成 `FollowUpDelta`，例如 `set_time_range`、`set_metrics`、`remove_dimensions`、`preserve`。

2. Semantic Layer
   将补全后的问题解析成 `SemanticState`：

   ```python
   SemanticState(
       domain="payment",
       metrics=["payment_gmv"],
       dimensions=["sy_hospital_name"],
       filters=["area_name LIKE '%华北%'"],
       time_range="this_month_mtd",
       top_n=10,
       grain="by_store_topn"
   )
   ```

   再转成 `SemanticContract`，给下游 planner 和 SQL generator 传递硬约束。

3. Hybrid Schema RAG
   Keyword 保证字段和指标精确命中，BM25 负责词法召回，Vector 负责语义召回，RRF 融合多路排名，rerank 做最终排序。最后通过 closure 补齐 `dp`、`is_valid`、`tenant_id`、`pay_date` 等低语义但 SQL 必需字段。

4. Schema Graph
   把召回结果组织成表、字段、关系图，保证 SQL 生成时字段来自可信 schema，join 关系可解释。

5. QueryPlanCoT
   使用推理模型或规则 fallback 生成可审计计划，不暴露隐藏思考链，而是输出四元组：`database`、`processing_objects`、`operation_instructions`、`output_target`。

6. Coder Model SQL Generation
   Coder 模型只负责根据 QueryPlanCoT 和 SchemaGraph 生成 MaxCompute SQL，不决定数据库连接、不绕过执行层。标准问题优先模板 SQL，复杂组合问题允许 LLM SQL 参与。

7. Safety Gate
   检查只读、表字段合法性、`dp` 分区、核销域 `is_valid=1`、支付域 `is_paydate_cash=0`、业务日期、TopN、MaxCompute 函数兼容性，以及城市、品项、大区、门店过滤是否保留。

8. Execution Router
   当前支持 `disabled / mock / sqlite / maxcompute`。执行请求携带 `database`，默认只暴露 `soyoung_dw`。这是一版轻量数据库 MCP 路由思想：模型只能在能力清单中规划，执行层根据注册 executor 路由；还没有升级成标准 MCP Server。

9. Reflection
   执行后做 Result Validation，检查空结果、列缺失、金额/人数全 NULL、TOP 形态和用户约束保真。失败后进入静态修复或模板兜底，并把失败原因写入 trace。

### 4.3 近期工程迭代

近期最核心的迭代是短期记忆和语义层。

**STAR 1：短期记忆**

**Situation：** 业务同事在真实问数里经常不会每轮都说完整问题。第一轮问“最近 30 天北京奇迹胶原核销收入 TOP5 门店”，第二轮可能只说“那上海呢”“top3”“支付金额呢”。
**Task：** 需要让系统理解当前追问是在继承上一轮，并明确修改了什么。
**Action：** 我引入 `FollowUpDelta`，把追问解析成结构化动作，而不是把历史问题和当前问题拼成字符串。CLI 输出 `delta`，便于调试和评测。
**Result：** P0 memory eval 12 个 case、34 轮全部通过；P1 复杂追问 4 个 case、8 轮全部通过，resolved、memory、selected、SQL constraints 均为 100%。

**STAR 2：语义层**

**Situation：** 通用模型能理解自然语言，但问数场景必须把“支付金额、支付收入、收款、流水”稳定映射到同一个字段，把“华北大区、华北地区、华北战区”稳定映射到 `area_name`。
**Task：** 需要让补全后的语义约束稳定进入 SQL，而不是只停留在自然语言层。
**Action：** 我在现有 `semantic_contract.py` 中引入轻量 `SemanticState`，将问题归一为 `domain / metrics / dimensions / filters / time_range / top_n / grain / calculation`，再生成 `SemanticContract`，传给 planner 和 SQL generator。
**Result：** 当前已支持核销、支付、待核销、渠道、新老客、品项、城市、大区、TopN、本周、本月等高频语义，并能让大区、门店、城市、品项等约束进入 SQL。

**STAR 3：LLM SQL 受控采纳**

**Situation：** LLM SQL 能提升泛化能力，但也会漏过滤、漏分区、用错日期函数或生成不安全语句。
**Task：** 需要让 LLM SQL 可以参与，但不能盲信。
**Action：** 我将 QueryPlanCoT、SchemaGraph、SemanticContract 和 Safety Gate 串起来，LLM SQL 只有通过门禁、执行层和结果校验才会被采纳；失败时走静态修复或模板兜底。
**Result：** 在 P0 前 10 条样本上，LLM SQL 采纳从 6/10 提升到 8/10，采纳率从 60% 提升到 80%，剩余失败也能归因到 `ORDER BY` 缺 `LIMIT`、占比除法缺 `NULLIF` 等明确问题。

## 5. Agent 怎么讲

这个项目更适合讲成 **Agentic Workflow 系统**，而不是完全开放式多智能体。

我会这样回答：

> 数据问数场景和通用聊天不一样，稳定性比自由探索更重要。所以我没有让 Agent 随机选择工具，而是采用 Plan-and-Execute + Reflection 范式：先把用户问题解析成语义状态和查询计划，再调用 schema 检索、SQL 生成、SQL 校验、MaxCompute 执行等工具，最后根据执行结果做反思、修复和回退。这样既保留了 Agent 的规划和工具调用能力，又能通过固定链路控制 SQL 风险。

如果面试官追问多 Agent，可以拆成 5 个角色：

1. 语义解析 Agent：识别指标、维度、时间、过滤、追问 delta。
2. 检索 Agent：从指标字典、schema、历史 SQL 中召回上下文。
3. Planner Agent：生成 QueryPlanCoT，明确要查什么、用什么表、怎么聚合。
4. Coder Agent：根据计划和 schema 生成 SQL。
5. Validator / Reflection Agent：检查 SQL 安全性、执行结果和口径一致性，必要时修复或回退。

但我也会强调：

> 当前实现不是标准 MCP 多工具生态，而是轻量能力边界和数据库路由。这样符合阶段目标：先把问数链路做稳，再考虑标准 MCP 化。

## 6. 项目亮点

1. 业务驱动，而不是模型驱动
   项目从经管中心真实取数需求出发，核心资产是指标字典、数仓表地图和口径评审机制。

2. Plan-and-Execute + Reflection
   先规划，再执行，再校验和修复，不让大模型直接裸写 SQL。

3. 语义层可解释
   将用户口语映射为标准 `SemanticState`，让“支付金额”“收款”“流水”归一到支付 GMV，让“大区/地区/战区”归一到 `area_name`。

4. Schema RAG 更适合 Text2SQL
   不是只做向量检索，而是 Keyword、BM25、Vector、RRF、rerank 和 closure 组合，兼顾召回率和字段精确性。

5. 短期记忆可评测
   用 `FollowUpDelta` 解释多轮追问，CLI 可以看到 delta，eval 可以检查 resolved question、继承轮次和 SQL 约束。

6. LLM SQL 受控采纳
   LLM 可以生成候选 SQL，但必须通过 Safety Gate、执行和结果校验，失败后有 repair/fallback。

7. 可落地到业务入口
   已接入飞书 CatData 机器人，符合业务同事真实工作场景。

## 7. 当前不足

### 7.1 后训练不足

目前主要依赖提示词、RAG、语义层和规则约束，还没有把真实问答、最终 SQL、修复轨迹和用户反馈沉淀成训练数据。后续可以做三步：

1. 收集真实问题、最终采纳 SQL、执行结果、人工修正，形成 SFT 数据。
2. 将错误修复过程整理成 preference 数据，让模型偏好标准口径和安全 SQL。
3. 对高频问数场景探索小模型微调或蒸馏，减少对长上下文和强推理模型的依赖。

面试说法：

> 我没有一开始就做后训练，因为数据质量比训练动作更重要。当前阶段我先搭日志、评测、反馈和修复闭环，把真实问题和标准 SQL 收集干净，再考虑 SFT 或偏好优化。

### 7.2 MCP 不足

当前已经有轻量 MCP 思想：在 CoT 生成前注入可用数据库和工具能力，生成后由 validator 校验 database、字段和关系，执行层也携带 `database` 作为路由键。默认只暴露 `soyoung_dw`，避免模型规划到没有权限的数据源。

但它还不是标准 MCP Server，没有实现：

1. `tools/list`
2. `tools/call`
3. resources
4. prompts
5. 多数据库权限和身份治理

下一步可以封装为标准工具：

1. `search_metric`：查指标定义、口径、SQL 片段。
2. `search_schema`：查表字段、字段解释、表关系。
3. `validate_sql`：检查只读、安全、分区、口径规则。
4. `execute_odps_sql`：执行 MaxCompute 查询并返回结构化结果。
5. `get_query_history`：读取用户历史问题和上下文。
6. `submit_feedback`：收集业务反馈和修正样例。

面试说法：

> MCP 的价值是把 Agent 能调用的数据工具标准化。当前我先实现轻量能力边界和数据库路由，保证链路稳定；等需要被飞书、Web、WorkBuddy 或其他 Agent 复用时，再升级成标准 MCP Server。

### 7.3 记忆体系的现状与不足

目前已经完成第一版短期记忆：用内存 dict 按 `session_id` 保存最近 3 轮结构化状态，包括 `time_range`、`metrics`、`dimensions`、`filters`、`top_n`、`template_id`、`last_sql`。当前追问会先解析 `FollowUpDelta`，再补全为完整问题进入 pipeline。

第一版边界：

1. 记忆只存在进程内，服务重启后会丢失。
2. 只保存最近 3 轮，没有做摘要压缩。
3. 当前主要覆盖高频追问，对复杂复合追问仍在补，例如“不要大区，看各门店”。
4. 没有长期用户偏好和组织级口径记忆。

后续可以分三层：

1. 短期记忆
   继续完善滑动窗口和摘要压缩，稳定处理换指标、换维度、删过滤、看整体等追问。

2. 长期记忆
   保存用户常用部门、常看指标、常看门店、常用输出形式。比如经营分析同事常看门店维度，战略咨询同事常看趋势和对比。

3. 组织记忆
   保存指标评审会确认过的标准口径、废弃口径、指标别名和冲突处理规则。

面试说法：

> 我没有一开始就做复杂记忆系统，而是先做结构化短期记忆。因为问数场景里最常见的不是长篇闲聊，而是“那上海呢”“本周呢”“支付金额呢”这类槽位替换。用结构化状态比把聊天记录全部塞进 prompt 更可控，也更容易评测。

## 8. 未来路线图

1. 第一阶段：语义层补全
   补更多指标语义簇，例如核销服务点、待核销服务点、支付人数、趋势、占比、对比；同时建立指标字典定期 review 机制，不知道的口径不强答，必要时返回澄清或升级人工确认。

2. 第二阶段：长短期记忆
   在 3 轮短期记忆基础上增加摘要压缩和长期用户偏好，让系统能记住不同业务同事常看的指标、门店、部门和输出习惯。

3. 第三阶段：Reflection 增强
   将 Safety Gate、执行失败、结果校验失败、用户反馈统一归因，沉淀为修复规则、评测 case 和后训练数据。

4. 第四阶段：权限和身份治理
   根据发送人的部门、角色、权限范围返回差异化回答，避免无权限数据被查询或展示。

5. 第五阶段：MCP 工具化
   把 schema 检索、指标查询、SQL 校验、ODPS 执行封装成标准 MCP 工具，支持飞书机器人、Web 页面和其他 Agent 复用。

6. 第六阶段：业务运营化
   收集业务语义习惯和许愿需求，例如占比、趋势、对比、异常归因；飞书卡片支持可选输出明细表或飞书表格链接，帮助业务团队二次分析。

7. 第七阶段：后训练闭环
   用真实问题、标准 SQL、人工修复、执行反馈和用户采纳情况探索 SFT、偏好优化或小模型蒸馏。

## 9. 面试追问回答

### 为什么不能直接让大模型写 SQL？

因为数仓查询的核心不是 SQL 语法，而是业务口径和字段选择。比如“支付金额”和“核销收入”在业务上都是金额，但一个走订单支付表和 `pay_date`，一个走核销表和 `executed_date`。直接让模型写 SQL，容易选错表、漏分区、漏过滤。我的做法是先用语义层和 schema RAG 约束上下文，再生成 SQL，并用 Safety Gate、执行和结果校验控制风险。

### 为什么要做语义层？

因为用户不会按字段名提问，而是用业务口语。语义层的作用是把“用户怎么说”归一成“系统怎么查”。比如“支付金额、支付收入、收款、流水”都归一到 `payment_gmv`，“华北大区、华北地区、华北战区”归一到 `area_name`。没有语义层，模型换个问法就可能理解偏；有语义层后，下游 SQL 生成拿到的是稳定的 `metrics / dimensions / filters / time_range`。

### 语义层和短期记忆有什么区别？

短期记忆解决“这一轮追问继承什么、修改什么”，语义层解决“修改后的完整问题对应哪些标准指标、维度和字段”。比如上一轮问“本月华北大区核销收入”，下一轮问“支付金额呢”，短期记忆识别这是 `domain_switch_to_payment`，补全为“本月华北大区支付GMV”；语义层再把它解析成 `payment_gmv + area_name LIKE 华北 + this_month_mtd`，最终进入 SQL。

### 为什么要做三路检索？

Text2SQL 的 schema 检索要求比普通文档 RAG 更高。关键词检索适合精确命中字段名和指标名，BM25 适合词法召回，向量检索适合理解业务同义表达，RRF 能融合不同召回器的排名，rerank 再做最终排序。最后 closure 补齐 `dp`、`is_valid`、`tenant_id` 这类 SQL 必需但语义不明显的字段。

### 为什么宽表优先？

业务同事的大部分问题是经营分析类聚合查询，优先用 DM 宽表和 DWS 汇总表可以减少 join 复杂度，也更贴近已经治理过的指标口径。只有需要明细排查或特殊字段时，才下钻到 DWD。

### 怎么保证指标口径一致？

一方面靠组织流程，每周和业务部门评审指标，把定义、计算逻辑、数据源和确认方沉淀进指标字典；另一方面靠系统约束，语义层先映射标准指标，SQL 生成必须引用标准字段，Safety Gate 和 Result Validation 再检查关键过滤和字段来源。

### 为什么 SQL 生成模型不决定 database？

因为 database 是权限和执行路由边界，不应该交给 SQL 生成模型自由决定。我的做法是在规划阶段注入可用数据库和工具能力，生成后由 validator 校验；SQL 模型只根据已校验的 QueryPlanCoT 和 SchemaGraph 写 SQL。这样能减少模型编造数据库、切换数据源或绕过执行层的风险，也为后续 MCP 化做准备。

### Prompt 优化怎么证明有效？

我没有只凭主观感觉改 prompt，而是用同一批 P0 样本做前后对比。最近一次只改推理模型和 SQL 生成模型提示词后，在 P0 前 10 条样本上，LLM SQL 生成保持 10/10，采纳从 6/10 提升到 8/10，采纳率从 60% 提升到 80%。同时保留失败归因，发现剩余问题主要是 `ORDER BY` 缺 `LIMIT` 和占比除法没有被 Safety Gate 认可，下一步应继续补安全规则和修复策略。

### 短期记忆怎么证明有效？

我做了专门的 memory follow-up eval，不只看单轮 SQL。评测会检查补全问题、是否使用记忆、继承轮次、模板路由和 SQL 关键约束。当前 P0 有 12 个 case、34 轮，P1 有 4 个 case、8 轮，最近一次本地验证 resolved、memory、selected、SQL constraints 都是 100%。

### 当前项目最大的不足是什么？

我认为主要有三个：第一，语义层还不完整，非收入类指标如核销服务点、待核销服务点还需要继续补；第二，还没有标准 MCP Server，只是轻量能力边界和数据库路由；第三，还没有后训练，真实问答和修复轨迹还需要继续沉淀成训练数据。

### 如果继续做，你优先做什么？

我会优先做三件事：第一，补齐语义层和长短期记忆，尤其是服务点、趋势、占比、对比这类语义簇；第二，增强 reflection，把执行失败、结果校验失败和用户反馈沉淀成修复规则和评测集；第三，落地权限管理和身份识别，让不同部门、不同角色获得差异化回答，并支持飞书卡片输出明细表链接。

## 10. 简历表述

数据智能部-数据架构组 AskData Agent 项目：面向经管中心战略咨询、商业分析、经营分析等 20-50 名业务用户的自然语言取数场景，基于连锁业务指标字典、数仓表地图和历史 SQL 构建 Agentic Text2SQL Workflow。项目采用 Plan-and-Execute + Reflection 范式，实现用户意图识别、短期记忆 FollowUpDelta、语义层 SemanticState、Hybrid Schema RAG、SchemaGraph、QueryPlanCoT、模板 SQL + LLM SQL 受控采纳、SQL Safety Gate、MaxCompute 只读执行、Result Validation 和 Repair/Fallback 闭环，并接入飞书 CatData 机器人作为业务入口。项目重点解决跨部门指标口径不一致、基础取数响应慢、数仓知识复用难等问题；通过 Keyword/BM25/Vector/RRF/rerank 提升 schema 召回，通过能力边界和数据库路由降低 SQL 风险，通过 golden eval、schema recall、LLM SQL 采纳率和 memory follow-up eval 持续评估效果。近期短期记忆 P0 评测 12 个 case、34 轮通过率 100%，P1 复杂追问 4 个 case、8 轮通过率 100%，LLM SQL 采纳率从 60% 提升到 80%。
