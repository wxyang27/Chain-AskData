const questionInput = document.querySelector("#question");
const generateButton = document.querySelector("#generate");
const planBlock = document.querySelector("#plan");
const sqlBlock = document.querySelector("#sql");
const validationBlock = document.querySelector("#validation");
const traceBlock = document.querySelector("#retrieval-trace");
const schemaGraphBlock = document.querySelector("#schema-graph");
const notesList = document.querySelector("#notes");
const copyButton = document.querySelector("#copy");
const demoList = document.querySelector("#demo-list");

const text = {
  noKnowledge: "\u672a\u547d\u4e2d\u77e5\u8bc6\u5757",
  metrics: "\u6307\u6807\u547d\u4e2d",
  fields: "\u5b57\u6bb5\u547d\u4e2d",
  tables: "\u8868\u547d\u4e2d",
  relations: "\u5173\u7cfb\u547d\u4e2d",
  examples: "\u6837\u4f8b\u547d\u4e2d",
  empty: "\u6682\u65e0\u547d\u4e2d",
  risks: "\u98ce\u9669\u63d0\u793a",
  generatingPlan: "\u6b63\u5728\u751f\u6210 QueryPlan...",
  generatingSql: "\u6b63\u5728\u751f\u6210 SQL...",
  validating: "\u6b63\u5728\u6821\u9a8c...",
  retrieving: "\u6b63\u5728\u68c0\u7d22\u77e5\u8bc6\u5e93...",
  buildingSchemaGraph: "\u6b63\u5728\u6784\u5efa SchemaGraph...",
  copied: "\u5df2\u590d\u5236",
  copy: "\u590d\u5236",
};

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
    traceBlock.textContent = text.noKnowledge;
    return;
  }

  traceBlock.innerHTML = "";
  const groups = [
    [text.metrics, context.metrics || []],
    [text.fields, context.fields || []],
    [text.tables, context.tables || []],
    [text.relations, context.relations || []],
    [text.examples, context.examples || []],
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
      empty.textContent = text.empty;
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
    heading.textContent = `${text.risks} (${context.risks.length})`;
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
    schemaGraphBlock.textContent = "\u6682\u65e0 SchemaGraph";
    return;
  }

  const summary = [
    `retriever: ${schemaGraph.retriever || "unknown"}`,
    `fields: ${schemaGraph.field_count ?? (schemaGraph.fields || []).length}`,
    `tables: ${schemaGraph.table_count ?? (schemaGraph.tables || []).length}`,
    `metrics: ${schemaGraph.metric_count ?? (schemaGraph.metrics || []).length}`,
    `relations: ${schemaGraph.relation_count ?? (schemaGraph.relations || []).length}`,
  ].join("\n");

  schemaGraphBlock.innerHTML = "";

  const summaryBlock = document.createElement("pre");
  summaryBlock.className = "schema-summary";
  summaryBlock.textContent = summary;

  const graphText = document.createElement("pre");
  graphText.className = "schema-text";
  graphText.textContent = schemaGraph.schema_graph_text || "\u672a\u751f\u6210 SchemaGraph Text";

  schemaGraphBlock.appendChild(summaryBlock);
  schemaGraphBlock.appendChild(graphText);
}

generateButton.addEventListener("click", async () => {
  const question = questionInput.value.trim();
  if (!question) {
    return;
  }

  planBlock.textContent = text.generatingPlan;
  sqlBlock.textContent = text.generatingSql;
  validationBlock.textContent = text.validating;
  traceBlock.textContent = text.retrieving;
  schemaGraphBlock.textContent = text.buildingSchemaGraph;
  notesList.innerHTML = "";

  const response = await fetch("/api/query", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({question}),
  });

  const data = await response.json();

  planBlock.textContent = JSON.stringify(data.query_plan, null, 2);
  sqlBlock.textContent = data.sql;
  validationBlock.textContent = JSON.stringify(data.validation, null, 2);
  renderRetrievalContext(data.retrieval_context);
  renderSchemaGraph(data.schema_graph);

  data.caliber_notes.forEach((note) => {
    const item = document.createElement("li");
    item.textContent = note;
    notesList.appendChild(item);
  });
});

copyButton.addEventListener("click", async () => {
  await navigator.clipboard.writeText(sqlBlock.textContent);
  copyButton.textContent = text.copied;
  window.setTimeout(() => {
    copyButton.textContent = text.copy;
  }, 1200);
});

loadDemoQueries();
