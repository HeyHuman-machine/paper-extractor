"""M8 表格视图模型测试。"""

from ui.view_models import failure_rows, result_rows, result_summary_rows, task_rows


def test_task_rows_calculates_success_rate_and_seconds() -> None:
    rows = task_rows(
        [
            {
                "id": 4,
                "created_at": "2026-08-12T12:00:00+00:00",
                "finished_at": "2026-08-12T12:01:00+00:00",
                "total_files": 4,
                "success_count": 3,
                "fail_count": 1,
                "duration_ms": 12500,
                "total_tokens": 800,
            }
        ]
    )
    assert rows[0]["任务 ID"] == 4
    assert rows[0]["成功率"] == "75%"
    assert rows[0]["耗时(s)"] == 12.5


def test_result_rows_joins_list_fields_for_table() -> None:
    rows = result_rows(
        [
            {
                "filename": "paper.pdf",
                "title": "论文",
                "authors": ["张三", "Alice"],
                "experimental_conditions": ["20 km SSMF", "QPSK"],
                "main_results": ["BER 达标"],
            }
        ]
    )
    assert rows[0]["作者"] == "张三\nAlice"
    assert rows[0]["实验条件"] == "20 km SSMF\nQPSK"


def test_result_summary_rows_keeps_only_readable_overview_columns() -> None:
    rows = result_summary_rows(
        [{"filename": "paper.pdf", "title": "论文", "year": 2025, "authors": ["张三"]}]
    )
    assert rows == [
        {
            "文件名": "paper.pdf",
            "标题": "论文",
            "年份": 2025,
            "期刊 / 会议": None,
            "方法名称": None,
            "重试": None,
            "Token": None,
        }
    ]


def test_failure_rows_keeps_diagnostic_fields() -> None:
    rows = failure_rows(
        [
            {
                "filename": "broken.pdf",
                "stage": "parse",
                "error_type": "CorruptedDocumentError",
                "error_msg": "文件损坏",
                "retry_count": 0,
            }
        ]
    )
    assert rows == [
        {
            "文件名": "broken.pdf",
            "失败阶段": "parse",
            "错误类型": "CorruptedDocumentError",
            "错误信息": "文件损坏",
            "重试次数": 0,
        }
    ]
