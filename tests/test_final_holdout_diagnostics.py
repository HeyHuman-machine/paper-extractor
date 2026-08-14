import pytest

from eval.final_holdout_diagnostics import arxiv_submission_year


def test_arxiv_submission_year_uses_modern_identifier_prefix() -> None:
    assert arxiv_submission_year("2402.00616") == 2024
    assert arxiv_submission_year("1804.04097") == 2018


def test_arxiv_submission_year_rejects_invalid_identifier() -> None:
    with pytest.raises(ValueError):
        arxiv_submission_year("not-an-id")
