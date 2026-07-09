const questionInput = document.querySelector("#question");
const generateButton = document.querySelector("#generate");
const planBlock = document.querySelector("#plan");
const llmStatusBlock = document.querySelector("#llm-status");
const sqlBlock = document.querySelector("#sql");
const validationBlock = document.querySelector("#validation");
const llmSqlBlock = document.querySelector("#llm-sql");
const llmMetaBlock = document.querySelector("#llm-meta");
const sqlSourceBadge = document.querySelector("#sql-source-badge");
const traceBlock = document.querySelector("#retrieval-trace");
const schemaGraphBlock = document.querySelector("#schema-graph");
const notesList = document.querySelector("#notes");
const copyButton = document.querySelector("#copy-template");
const demoList = document.querySelector("#demo-list");

async function loadDemoQueries() {
  const response = await fetch("/api/demo-queries");
  const demoQueries = await response.json();

  demoList.innerHTML = "";
  demoQueries.forEach((demo) => {
    const button = document.createElement("button");
    button.className = "demo-item";
    button.type = "button";
    button.textContent = demo.question;
    button.title = `${demo.case_id} - ${demo.business_domain}`;
    button.addEventListener("click", () => {
      questionInput.value = demo.question;
    });
    demoList.appendChild(button);
  });
}

function renderRetrievalContext(context) {
  if (!context) {
    traceBlock.textContent = "no knowledge";
    return;
  }

  traceBlock.innerHTML = "";
  const groups = [
    ["metrics", context.metrics || []],
    ["fields", context.fields || []],
    ["tables", context.tables || []],
    ["relations", context.relations || []],
    ["examples", context.examples || []],
  ];

  groups.forEach(([title, items]) => {
    const section = document.createElement("div");
    section.className = "trace-section";

    const heading = document.createElement("div");
    heading.className = "trace-section-title";
    heading.textContent = `${title} (${items.length})`;
    section.appendChild(heading);

    if (items.length === 0) {
      const empty = document.createElement("p");
      empty.className = "trace-empty";
      empty.textContent = "empty";
      section.appendChild(empty);
    }

    items.forEach((item, index) => {
      section.appendChild(renderTraceItem(item, index));
    });

    traceBlock.appendChild(section);
  });

  if (context.risks && context.risks.length > 0) {
    const section = document.createElement("div");
    section.className = "trace-section";
    const heading = document.createElement("div");
    heading.className = "trace-section-title";
    heading.textContent = `risks (${context.risks.length})`;
    section.appendChild(heading);
    context.risks.forEach((risk) => {
      const item = document.createElement("p");
      item.className = "trace-risk";
      item.textContent = risk;
      section.appendChild(item);
    });
    traceBlock.appendChild(section);
  }
}

function renderTraceItem(item, index) {
  const metadata = item.metadata || {};
  const card = document.createElement("div");
  card.className = "trace-item";

  const title = document.createElement("div");
  title.className = "trace-title";
  title.textContent = `${index + 1}. ${metadata.asset_type || "unknown"} - score ${item.rerank_score ?? 0}`;

  const meta = document.createElement("pre");
  meta.className = "trace-meta";
  meta.textContent = JSON.stringify(metadata, null, 2);

  const documentText = document.createElement("p");
  documentText.textContent = item.document;

  card.appendChild(title);
  card.appendChild(meta);
  card.appendChild(documentText);
  return card;
}

function renderSchemaGraph(schemaGraph) {
  if (!schemaGraph) {
    schemaGraphBlock.textContent = "No SchemaGraph";
    return;
  }

  const summary = [
    `retriever: ${schemaGraph.retriever || "unknown"}`,
    `fields: ${schemaGraph.field_count ?? (schemaGraph.fields || []).length}`,
    `tables: ${schemaGraph.table_count ?? (schemaGraph.tables || []).length}`,
    `metrics: ${schemaGraph.metric_count ?? (schemaGraph.metrics || []).length}`,
    `relations: ${schemaGraph.relation_count ?? (schemaGraph.relations || []).length}`,
    `supplemented: ${(schemaGraph.supplemented_fields || []).join(", ")}`,
  ].join("\n");

  schemaGraphBlock.innerHTML = "";

  const summaryBlock = document.createElement("pre");
  summaryBlock.className = "schema-summary";
  summaryBlock.textContent = summary;

  const graphText = document.createElement("pre");
  graphText.className = "schema-text";
  graphText.textContent = schemaGraph.schema_graph_text || "No SchemaGraph Text";

  schemaGraphBlock.appendChild(summaryBlock);
  schemaGraphBlock.appendChild(graphText);
}

function renderLlmStatus(queryPlan) {
  if (!queryPlan) {
    llmStatusBlock.textContent = "No LLM status";
    return;
  }

  const status = {
    llm_enabled: queryPlan.llm_enabled ?? "N/A",
    llm_adopted: queryPlan.llm_adopted ?? "N/A",
    llm_model: queryPlan.llm_model || "N/A",
    validation_passed: queryPlan.llm_validation_passed ?? "N/A",
    validation_errors: queryPlan.llm_validation_errors || [],
    latency_ms: queryPlan.llm_latency_ms ?? "N/A",
    repair_count: queryPlan.llm_repair_count ?? 0,
    fallback_reason: queryPlan.llm_fallback_reason || "",
  };
  llmStatusBlock.textContent = JSON.stringify(status, null, 2);
}

function formatSql(sql) {
  if (!sql) return "";
  return sql
    .replace(/\s+(FROM|WHERE|AND|OR|ON|LEFT JOIN|RIGHT JOIN|INNER JOIN|JOIN|GROUP BY|ORDER BY|HAVING|LIMIT|UNION)\b/gi, "\n$1")
    .replace(/^\n/, "")
    .trim();
}

function extractSqlTokens(sql) {
  const tokens = { tables: [], fields: [], hasJoin: false, hasGroupBy: false, hasOrderBy: false, hasLimit: false, hasWhere: false };
  if (!sql) return tokens;
  const upper = sql.toUpperCase();
  tokens.hasJoin = /JOIN\s/i.test(upper);
  tokens.hasGroupBy = /GROUP\s+BY/i.test(upper);
  tokens.hasOrderBy = /ORDER\s+BY/i.test(upper);
  tokens.hasLimit = /LIMIT\s+\d+/i.test(upper);
  tokens.hasWhere = /\bWHERE\b/i.test(upper);

  const tableRe = /(?:FROM|JOIN)\s+\w+\.(\w+)/gi;
  let m;
  while ((m = tableRe.exec(sql)) !== null) {
    if (!tokens.tables.includes(m[1])) tokens.tables.push(m[1]);
  }

  const fieldRe = /\b(\w+\.\w+)\b/g;
  while ((m = fieldRe.exec(sql)) !== null) {
    const f = m[1];
    if (!/^(soyoung_dw|DATE_SUB|CURRENT_DATE|DATE_ADD|YEARWEEK|TO_DATE|CONCAT|CAST|NULLIF|COALESCE)\./i.test(f)) {
      if (!tokens.fields.includes(f)) tokens.fields.push(f);
    }
  }

  return tokens;
}

function renderCompare(templateSql, llmSql, validation) {
  const cmp = document.querySelector("#compare-result");
  if (!cmp) return;

  const t = extractSqlTokens(templateSql);
  const l = extractSqlTokens(llmSql);

  if (!templateSql || !llmSql) {
    cmp.innerHTML = "<p class='cmp-waiting'>等待双方 SQL 生成后对比...</p>";
    return;
  }

  const matchCount = l.fields.filter((f) => {
    const short = f.split(".").slice(-2).join(".");
    return t.fields.some((tf) => tf.split(".").slice(-2).join(".") === short);
  }).length;

  const totalDims = 6;
  let matchDims = 0;
  const rows = [
    ["数据表", t.tables.join(" / "), l.tables.join(" / ")],
    ["表关联", t.hasJoin ? "JOIN" : "单表", l.hasJoin ? "JOIN" : "单表"],
    ["筛选条件", t.hasWhere ? "有" : "无", l.hasWhere ? "有" : "无"],
    ["分组聚合", t.hasGroupBy ? "有" : "无", l.hasGroupBy ? "有" : "无"],
    ["排序", t.hasOrderBy ? "有" : "无", l.hasOrderBy ? "有" : "无"],
    ["行数限制", t.hasLimit ? "有" : "无", l.hasLimit ? "有" : "无"],
  ];

  let html = "<table class='compare-table'>";
  html += "<tr><th></th><th>模板 SQL</th><th>LLM SQL</th></tr>";
  rows.forEach(([dim, tVal, lVal]) => {
    const ok = String(tVal) === String(lVal);
    if (ok) matchDims++;
    const icon = ok ? "✔" : "✘";
    const cls = ok ? "cmp-ok" : "cmp-no";
    html += `<tr><td class="cmp-dim">${dim}</td><td>${tVal}</td><td class="${cls}">${icon} ${lVal}</td></tr>`;
  });
  html += "</table>";

  const gatePassed = validation && validation.passed;
  const score = Math.round((matchDims / totalDims) * 100);
  html += `<div class="cmp-summary">`;
  html += `<span class="cmp-score">${score}% 结构一致</span> `;
  html += `<span>(${matchDims}/${totalDims} 项匹配，${matchCount} 个字段对齐)</span>`;
  if (gatePassed) {
    html += ` <span class="badge badge-active">门禁通过</span>`;
  } else {
    html += ` <span class="badge badge-shadow">门禁未通过</span>`;
  }
  html += `</div>`;

  cmp.innerHTML = html;
}

function renderLlmSql(data) {
  if (!llmSqlBlock) return;

  const detail = data.llm_sql_detail || {};
  const validation = data.llm_sql_validation || {};

  // Format template SQL for display
  sqlBlock.textContent = formatSql(data.template_sql || data.sql || "");

  if (!detail.generated) {
    llmSqlBlock.textContent = detail.error || "LLM SQL not generated";
    if (sqlSourceBadge) { sqlSourceBadge.textContent = "模板"; sqlSourceBadge.className = "badge badge-active"; }
    return;
  }

  llmSqlBlock.textContent = formatSql(data.llm_sql || "");

  const meta = [];
  if (detail.explanation) meta.push(detail.explanation);
  if (!validation.passed && validation.errors.length) {
    meta.push("门禁错误: " + validation.errors.join("; "));
  }
  if (llmMetaBlock) llmMetaBlock.textContent = meta.join("\n") || "通过所有门禁检查";

  if (sqlSourceBadge) {
    if (data.llm_sql_adopted) {
      sqlSourceBadge.textContent = "LLM";
      sqlSourceBadge.className = "badge badge-llm";
    } else if (validation.passed) {
      sqlSourceBadge.textContent = "模板";
      sqlSourceBadge.className = "badge badge-active";
    } else {
      sqlSourceBadge.textContent = "模板（门禁未过）";
      sqlSourceBadge.className = "badge badge-shadow";
    }
  }

  renderCompare(data.template_sql || data.sql, data.llm_sql, validation);
}

generateButton.addEventListener("click", async () => {
  const question = questionInput.value.trim();
  if (!question) {
    return;
  }

  planBlock.textContent = "generating Plan...";
  llmStatusBlock.textContent = "checking LLM...";
  sqlBlock.textContent = "generating SQL...";
  validationBlock.textContent = "validating...";
  traceBlock.textContent = "retrieving...";
  schemaGraphBlock.textContent = "building SchemaGraph...";
  if (llmSqlBlock) llmSqlBlock.textContent = "generating LLM SQL...";
  notesList.innerHTML = "";

  try {
    const response = await fetch("/api/query", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({question}),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || `HTTP ${response.status}`);
    }

    planBlock.textContent = JSON.stringify(data.query_plan, null, 2);
    renderLlmStatus(data.query_plan);
    sqlBlock.textContent = data.template_sql || data.sql;
    validationBlock.textContent = JSON.stringify(data.validation, null, 2);
    renderLlmSql(data);
    renderRetrievalContext(data.retrieval_context);
    renderSchemaGraph(data.schema_graph);

    (data.caliber_notes || []).forEach((note) => {
      const item = document.createElement("li");
      item.textContent = note;
      notesList.appendChild(item);
    });
  } catch (error) {
    const message = `Error: ${error.message}`;
    planBlock.textContent = message;
    llmStatusBlock.textContent = message;
    sqlBlock.textContent = "";
    validationBlock.textContent = message;
    if (llmSqlBlock) llmSqlBlock.textContent = message;
    traceBlock.textContent = message;
    schemaGraphBlock.textContent = message;
  }
});

copyButton.addEventListener("click", async () => {
  await navigator.clipboard.writeText(sqlBlock.textContent);
  copyButton.textContent = "Copied";
  window.setTimeout(() => {
    copyButton.textContent = "Copy";
  }, 1200);
});

loadDemoQueries();
