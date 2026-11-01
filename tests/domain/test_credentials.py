import pytest

from app.domain.credentials.entities import Credential, Integration


def test_labels() -> None:
    assert [i.label for i in Integration] == ["Linear", "GitHub", "OpenRouter"]


def test_hint_is_the_last_four_characters() -> None:
    assert Credential(Integration.LINEAR, "lin_api_abcd1234").hint == "…1234"


def test_short_secret_hides_its_hint() -> None:
    assert Credential(Integration.LINEAR, "short_key").hint == "…"


@pytest.mark.parametrize("secret", ["", "   "])
def test_blank_secret_is_rejected(secret: str) -> None:
    with pytest.raises(ValueError, match="secret"):
        Credential(Integration.LINEAR, secret)


def test_github_needs_an_owner() -> None:
    with pytest.raises(ValueError, match="owner"):
        Credential(Integration.GITHUB, "ghp_x")


def test_openrouter_needs_a_model() -> None:
    with pytest.raises(ValueError, match="model"):
        Credential(Integration.OPENROUTER, "sk-or-x")


def test_linear_takes_neither_owner_nor_model() -> None:
    with pytest.raises(ValueError, match="owner"):
        Credential(Integration.LINEAR, "lin", owner="acme")
    with pytest.raises(ValueError, match="model"):
        Credential(Integration.LINEAR, "lin", model="m")


def test_valid_github_and_openrouter() -> None:
    assert Credential(Integration.GITHUB, "ghp_x", owner="acme").owner == "acme"
    assert Credential(Integration.OPENROUTER, "sk", model="m").model == "m"


def test_repr_never_shows_the_secret() -> None:
    assert "lin_api_abcd1234" not in repr(Credential(Integration.LINEAR, "lin_api_abcd1234"))
