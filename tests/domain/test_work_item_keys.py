from app.domain.codebases.keys import work_item_keys


def test_work_item_keys_reads_lower_case_branch() -> None:
    assert work_item_keys("murilo/ops-123-fix-login") == ("OPS-123",)


def test_work_item_keys_dedupes_across_texts_in_order() -> None:
    assert work_item_keys("Fix OPS-123 and ENG-7", "ops-123") == ("OPS-123", "ENG-7")


def test_work_item_keys_reads_bracketed_and_underscored() -> None:
    assert work_item_keys("[OPS-1] title", "ops-2_fix") == ("OPS-1", "OPS-2")


def test_work_item_keys_ignores_glued_or_incomplete_tokens() -> None:
    assert work_item_keys("noops123", "OPS-", "OPS-123abc") == ()
