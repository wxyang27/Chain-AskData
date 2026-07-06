const questionInput = document.querySelector("#question");
const generateButton = document.querySelector("#generate");
const planBlock = document.querySelector("#plan");
const sqlBlock = document.querySelector("#sql");
const validationBlock = document.querySelector("#validation");
const notesList = document.querySelector("#notes");
const copyButton = document.querySelector("#copy");

document.querySelectorAll(".demo-item").forEach((button) => {
  button.addEventListener("click", () => {
    questionInput.value = button.textContent;
  });
});

generateButton.addEventListener("click", async () => {
  const question = questionInput.value.trim();
  if (!question) {
    return;
  }

  planBlock.textContent = "正在生成 QueryPlan...";
  sqlBlock.textContent = "正在生成 SQL...";
  validationBlock.textContent = "正在校验...";
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

  data.caliber_notes.forEach((note) => {
    const item = document.createElement("li");
    item.textContent = note;
    notesList.appendChild(item);
  });
});

copyButton.addEventListener("click", async () => {
  await navigator.clipboard.writeText(sqlBlock.textContent);
  copyButton.textContent = "已复制";
  window.setTimeout(() => {
    copyButton.textContent = "复制";
  }, 1200);
});
