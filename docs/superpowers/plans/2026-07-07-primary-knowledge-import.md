# 原始知识批量导入 实施计划

> **给后续执行者：**本计划用于批量导入经管中心 Word/Excel 原始文档，转化为结构化、可版本化的知识资产和 Chroma 可消费的文档块。

**目标：**批量导入已上传的经管中心 Word/Excel 文档，转化为结构化知识资产和 Chroma 知识块。

**架构：**新增 `app/knowledge_importer` 包，从 `docs/primary_knowledge` 读取源文档，将规范化后的 JSON 资产写入 `knowledge/generated`，并暴露生成块加载器供现有知识索引器消费。Excel 行转为指标/用户画像/维度/看板/数据源资产；Word 文档转为库表资产和业务分析 playbook 资产，均保留来源追溯元数据。

**技术栈：**Python、`openpyxl`、`python-docx`、JSON 资产、现有 `KnowledgeChunk` 和 Chroma 初始化流程。

---

### 任务 1：原始知识导入测试

**文件：**
- 新建：`tests/test_primary_knowledge_import.py`

- [ ] **步骤 1：编写失败测试**

```python
from pathlib import Path

from app.knowledge_importer.pipeline import PrimaryKnowledgeImporter


def test_imports_uploaded_primary_knowledge_into_structured_assets(tmp_path):
    source_dir = Path("docs/primary_knowledge")
    assert source_dir.exists()

    result = PrimaryKnowledgeImporter().import_to_directory(source_dir, tmp_path)

    assert result.counts["metrics"] == 151
    assert result.counts["user_profile_fields"] == 112
    assert result.counts["dimensions"] == 10
    assert result.counts["data_sources"] == 7
    assert result.counts["dashboard_metrics"] == 288
    assert result.counts["tables"] >= 49
    assert result.counts["business_playbooks"] > 10
```

- [ ] **步骤 2：运行测试确认失败**

运行：`pytest tests/test_primary_knowledge_import.py -q`
预期：FAIL，报错 `ModuleNotFoundError: No module named 'app.knowledge_importer'`。

### 任务 2：导入器实现

**文件：**
- 新建：`app/knowledge_importer/__init__.py`
- 新建：`app/knowledge_importer/models.py`
- 新建：`app/knowledge_importer/excel_loader.py`
- 新建：`app/knowledge_importer/docx_loader.py`
- 新建：`app/knowledge_importer/pipeline.py`
- 修改：`requirements.txt`
- 修改：`pyproject.toml`

- [ ] **步骤 1：实现 Excel 行资产加载**

使用 `openpyxl` 读取已上传的指标字典工作簿。规范化来自"原子指标字典""衍生指标字典""用户画像字段""维度字典""数据源目录""看板指标映射"等 Sheet 的行数据。

- [ ] **步骤 2：实现 Word 资产加载**

使用 `python-docx` 读取数据库文档和分析拆解文档。用正则提取表名，从前缀推断表分层，将表/playbook 行捕获为结构化文本，并保留 `source_file`/`source_index` 溯源字段。

- [ ] **步骤 3：写入生成 JSON 资产**

在输出目录下写入 JSON 文件：
- `metrics_full.json`
- `user_profile_fields.json`
- `dimensions.json`
- `data_sources.json`
- `dashboard_metrics.json`
- `tables_full.json`
- `business_playbooks.json`

- [ ] **步骤 4：运行导入测试**

运行：`pytest tests/test_primary_knowledge_import.py -q`
预期：PASS。

### 任务 3：生成块加载器测试

**文件：**
- 新建：`tests/test_generated_knowledge_chunks.py`

- [ ] **步骤 1：编写失败测试**

```python
from pathlib import Path

from app.knowledge_importer.pipeline import PrimaryKnowledgeImporter
from app.knowledge_importer.chunker import load_generated_knowledge_chunks


def test_generated_assets_become_searchable_knowledge_chunks(tmp_path):
    PrimaryKnowledgeImporter().import_to_directory(Path("docs/primary_knowledge"), tmp_path)

    chunks = load_generated_knowledge_chunks(tmp_path)
    chunk_ids = {chunk.chunk_id for chunk in chunks}

    assert "generated_metric:A002" in chunk_ids
    assert any(chunk.metadata["asset_type"] == "table" for chunk in chunks)
    assert any(chunk.metadata["asset_type"] == "business_playbook" for chunk in chunks)
    assert any("核销收入" in chunk.document for chunk in chunks)
```

- [ ] **步骤 2：运行测试确认失败**

运行：`pytest tests/test_generated_knowledge_chunks.py -q`
预期：FAIL，报错 `ModuleNotFoundError` 或缺少 `chunker`。

### 任务 4：分块器与现有加载器集成

**文件：**
- 新建：`app/knowledge_importer/chunker.py`
- 修改：`app/knowledge_indexer/loader.py`

- [ ] **步骤 1：实现生成知识分块器**

创建 `KnowledgeChunk` 记录，仅使用标量元数据。每条指标的 SQL 和公式文本保留在一个 chunk 中；使用 `generated_metric:<id>`、`generated_table:<name>` 等稳定的 chunk ID。

- [ ] **步骤 2：将生成块纳入常规知识加载**

扩展 `load_knowledge_chunks()`，当 `knowledge/generated` 存在时追加生成块。

- [ ] **步骤 3：运行生成块测试**

运行：`pytest tests/test_generated_knowledge_chunks.py -q`
预期：PASS。

### 任务 5：生成本地资产并验证全量测试

**文件：**
- 命令生成：`knowledge/generated/*.json`

- [ ] **步骤 1：运行导入器**

运行：`python -m app.knowledge_importer.pipeline`
预期：JSON 资产写入 `knowledge/generated`。

- [ ] **步骤 2：运行聚焦测试**

运行：`pytest tests/test_primary_knowledge_import.py tests/test_generated_knowledge_chunks.py -q`
预期：PASS。

- [ ] **步骤 3：运行全量测试**

运行：`pytest -q`
预期：PASS。
