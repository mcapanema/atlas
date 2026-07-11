from app.domain.advisor.port import AdvisorError
from app.domain.sync.port import DataSourceError


def test_advisor_error_is_not_a_value_error() -> None:
    # pydantic ValidationError IS a ValueError; if these were ValueError
    # subclasses, the global ValueError handler would blame the client (422)
    # for an upstream failure instead of returning 502.
    assert issubclass(AdvisorError, Exception)
    assert not issubclass(AdvisorError, ValueError)


def test_data_source_error_is_not_a_value_error() -> None:
    assert issubclass(DataSourceError, Exception)
    assert not issubclass(DataSourceError, ValueError)
