import json
from datetime import datetime
from types import SimpleNamespace

from app.feishu_bot.base_logger import FeishuBaseLogger, FeishuLogEntry


def test_base_logger_writes_field_ids(monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return SimpleNamespace(returncode=0, stdout="{}", stderr="")

    monkeypatch.setattr("app.feishu_bot.base_logger.subprocess.run", fake_run)

    logger = FeishuBaseLogger()
    logger.enabled = True
    logger.write(
        FeishuLogEntry(
            created_at=datetime(2026, 7, 24, 17, 30, 0),
            chat_type="group",
            sender_id="ou_user",
            sender_name="Soyoung",
            chat_id="oc_group",
            chat_name="AskData 测试群",
            question="本月华东大区支付GMV",
            intent="data_query",
            status="成功",
            execution_mode="disabled",
            execution_status="skipped",
            sql_source="template",
            row_count=0,
            elapsed_seconds=1.23,
            reply_summary="已生成 SQL",
            sql="SELECT 1",
        )
    )

    payload = json.loads(captured["cmd"][captured["cmd"].index("--json") + 1])

    assert "fldDHZ621M" in payload["fields"]
    assert "fldHjSpT3I" in payload["fields"]
    assert "fldS8Pv72o" in payload["fields"]
    assert "时间" not in payload["fields"]
    assert payload["rows"][0][payload["fields"].index("fldHjSpT3I")] == "本月华东大区支付GMV"
    assert payload["rows"][0][payload["fields"].index("fldS8Pv72o")] == 0
