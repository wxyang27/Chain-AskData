from app.execution.factory import create_sql_executor
from app.execution.objects import SqlExecutionRequest
from app.execution.sqlite_executor import SQLiteSqlExecutor


def test_disabled_executor_skips_sql():
    executor = create_sql_executor("disabled")

    result = executor.execute(SqlExecutionRequest(sql="SELECT 1"))

    assert result.enabled is False
    assert result.mode == "disabled"
    assert result.status == "skipped"
    assert result.row_count == 0
    assert result.error == "execution_disabled"


def test_mock_executor_returns_sample_rows():
    executor = create_sql_executor("mock")

    result = executor.execute(
        SqlExecutionRequest(
            sql="SELECT sy_hospital_name AS 门店, SUM(exe_income) AS 核销收入 FROM t LIMIT 2",
            max_rows=100,
        )
    )

    assert result.enabled is True
    assert result.mode == "mock"
    assert result.status == "success"
    assert result.dry_run is True
    assert result.columns == ["门店", "核销收入"]
    assert result.row_count == 2
    assert len(result.sample_rows) == 2
    assert "门店" in result.sample_rows[0]


def test_sqlite_executor_executes_local_select(tmp_path):
    import sqlite3

    db_path = tmp_path / "demo.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE demo (id INTEGER, name TEXT)")
        conn.execute("INSERT INTO demo VALUES (1, 'alpha')")
        conn.commit()

    executor = SQLiteSqlExecutor(str(db_path))
    result = executor.execute(SqlExecutionRequest(sql="SELECT id, name FROM demo", max_rows=10))

    assert result.status == "success"
    assert result.dry_run is False
    assert result.columns == ["id", "name"]
    assert result.sample_rows == [{"id": 1, "name": "alpha"}]
    assert result.row_count == 1
