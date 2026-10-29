from app.domain.codebases.keys import work_item_keys


def test_work_item_keys_reads_lower_case_branch() -> None:
    assert work_item_keys("murilo/dep-123-fix-login") == ("DEP-123",)


def test_work_item_keys_dedupes_across_texts_in_order() -> None:
    assert work_item_keys("Fix DEP-123 and ENG-7", "dep-123") == ("DEP-123", "ENG-7")


def test_work_item_keys_reads_bracketed_and_underscored() -> None:
    assert work_item_keys("[DEP-1] title", "dep-2_fix") == ("DEP-1", "DEP-2")


def test_work_item_keys_ignores_glued_or_incomplete_tokens() -> None:
    assert work_item_keys("nodep123", "DEP-", "DEP-123abc") == ()
