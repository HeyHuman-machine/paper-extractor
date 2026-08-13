"""V6 主结果精修单元测试，不访问网络。"""

import json

from app.result_refiner import ResultRefiner
from test_extractor import FakeLLMClient, response


def test_result_refiner_returns_only_result_list() -> None:
    client = FakeLLMClient(
        [response(json.dumps({"main_results": ["BER: 1e-3 | condition: 20 km"]}))]
    )
    paper = "TITLE\n" + ("background\n" * 300) + "BER: 1e-3 at 20 km."

    refined = ResultRefiner(client, max_retries=0).refine(paper, 4000)

    assert refined.success is True
    assert refined.main_results == ["BER: 1e-3 | condition: 20 km"]
    assert "结果指标证据" in client.received_messages[0][-1]["content"]


def test_result_refiner_failure_is_reported_for_baseline_fallback() -> None:
    client = FakeLLMClient([response("not json")])

    refined = ResultRefiner(client, max_retries=0).refine("paper text", 800)

    assert refined.success is False
    assert refined.main_results is None
    assert refined.error is not None
