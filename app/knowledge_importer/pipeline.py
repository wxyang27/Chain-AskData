import json
from pathlib import Path
from typing import Any

from app.knowledge_importer.docx_loader import AnalysisDocxLoader, DatabaseDocxLoader
from app.knowledge_importer.excel_loader import IndicatorWorkbookLoader
from app.knowledge_importer.models import ImportResult


DEFAULT_SOURCE_DIR = Path("docs/primary_knowledge")
DEFAULT_OUTPUT_DIR = Path("knowledge/generated")


class PrimaryKnowledgeImporter:
    """Batch import uploaded primary knowledge documents into generated JSON assets."""

    def import_to_directory(
        self,
        source_dir: Path = DEFAULT_SOURCE_DIR,
        output_dir: Path = DEFAULT_OUTPUT_DIR,
    ) -> ImportResult:
        source_dir = Path(source_dir)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        workbook_assets = IndicatorWorkbookLoader().load(self._find_indicator_workbook(source_dir))
        tables = DatabaseDocxLoader().load_tables(
            self._find_database_docx(source_dir),
            workbook_assets["data_sources"],
        )
        playbooks = AnalysisDocxLoader().load_playbooks(self._find_analysis_docx(source_dir))

        assets = {
            "metrics_full.json": workbook_assets["metrics"],
            "user_profile_fields.json": workbook_assets["user_profile_fields"],
            "dimensions.json": workbook_assets["dimensions"],
            "data_sources.json": workbook_assets["data_sources"],
            "dashboard_metrics.json": workbook_assets["dashboard_metrics"],
            "tables_full.json": tables,
            "business_playbooks.json": playbooks,
        }

        files: dict[str, Path] = {}
        for filename, records in assets.items():
            path = output_dir / filename
            path.write_text(
                json.dumps(records, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            files[filename] = path

        return ImportResult(
            output_dir=output_dir,
            counts={
                "metrics": len(workbook_assets["metrics"]),
                "user_profile_fields": len(workbook_assets["user_profile_fields"]),
                "dimensions": len(workbook_assets["dimensions"]),
                "data_sources": len(workbook_assets["data_sources"]),
                "dashboard_metrics": len(workbook_assets["dashboard_metrics"]),
                "tables": len(tables),
                "business_playbooks": len(playbooks),
            },
            files=files,
        )

    def _find_indicator_workbook(self, source_dir: Path) -> Path:
        return self._find_one(source_dir, "*.xlsx", "指标字典")

    def _find_database_docx(self, source_dir: Path) -> Path:
        return self._find_one(source_dir, "*.docx", "数据库表")

    def _find_analysis_docx(self, source_dir: Path) -> Path:
        return self._find_one(source_dir, "*.docx", "分析拆解")

    def _find_one(self, source_dir: Path, pattern: str, keyword: str) -> Path:
        matches = [path for path in source_dir.glob(pattern) if keyword in path.name]
        if len(matches) != 1:
            raise FileNotFoundError(
                f"Expected exactly one {pattern} file containing {keyword}, found {len(matches)}"
            )
        return matches[0]


def main() -> None:
    result = PrimaryKnowledgeImporter().import_to_directory()
    print(f"Imported primary knowledge into {result.output_dir}")
    for asset_name, count in result.counts.items():
        print(f"{asset_name}: {count}")


if __name__ == "__main__":
    main()
