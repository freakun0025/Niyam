from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import SecretFileError, Settings


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("NIYAM_APP_VERSION", "NIYAM_LOG_LEVEL", "NIYAM_QDRANT_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def test_reads_values_from_prefixed_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NIYAM_APP_VERSION", "a1b2c3d")
    monkeypatch.setenv("NIYAM_LOG_LEVEL", "DEBUG")

    settings = Settings()

    assert settings.app_version == "a1b2c3d"
    assert settings.log_level == "DEBUG"


def test_rejects_unknown_log_level(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NIYAM_LOG_LEVEL", "LOUD")

    with pytest.raises(ValidationError):
        Settings()


def test_secret_file_is_read_and_stripped(tmp_path: Path) -> None:
    secret = tmp_path / "qdrant"
    secret.write_text("from-vault\n", encoding="utf-8")

    settings = Settings(qdrant_api_key_file=secret)

    assert settings.resolved_qdrant_api_key() == "from-vault"


def test_secret_file_wins_over_dev_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = tmp_path / "qdrant"
    secret.write_text("from-vault", encoding="utf-8")
    monkeypatch.setenv("NIYAM_QDRANT_API_KEY", "dev-only-key")

    settings = Settings(qdrant_api_key_file=secret)

    assert settings.resolved_qdrant_api_key() == "from-vault"


def test_secret_file_rotation_is_picked_up(tmp_path: Path) -> None:
    secret = tmp_path / "qdrant"
    secret.write_text("first", encoding="utf-8")
    settings = Settings(qdrant_api_key_file=secret)
    assert settings.resolved_qdrant_api_key() == "first"

    secret.write_text("second", encoding="utf-8")

    assert settings.resolved_qdrant_api_key() == "second"


def test_missing_file_falls_back_to_dev_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NIYAM_QDRANT_API_KEY", "dev-only-key")

    settings = Settings(qdrant_api_key_file=tmp_path / "missing")

    assert settings.resolved_qdrant_api_key() == "dev-only-key"


def test_no_file_and_no_variable_means_no_key(tmp_path: Path) -> None:
    settings = Settings(qdrant_api_key_file=tmp_path / "missing")

    assert settings.resolved_qdrant_api_key() is None


def test_empty_secret_file_is_an_error(tmp_path: Path) -> None:
    secret = tmp_path / "qdrant"
    secret.write_text(" \n", encoding="utf-8")

    settings = Settings(qdrant_api_key_file=secret)

    with pytest.raises(SecretFileError):
        settings.resolved_qdrant_api_key()


def test_dev_key_is_hidden_from_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NIYAM_QDRANT_API_KEY", "do-not-print-me")

    assert "do-not-print-me" not in repr(Settings())
