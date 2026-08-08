from __future__ import annotations

from pathlib import Path

import pytest

from reefproof.settings import (
    AlertsSettings,
    ApiSettings,
    ConsoleAdapterSettings,
    HomeAssistantAdapterSettings,
    ReefProofSettings,
    Settings,
    StorageSettings,
    load_settings,
)


def test_settings_defaults() -> None:
    settings = Settings()

    assert settings.timezone == "America/New_York"
    assert settings.data_directory == Path(".local/data")
    assert settings.log_level == "INFO"
    assert settings.mode == "fixture"
    assert settings.json_logs is False
    assert settings.hydros.enabled is False
    assert settings.api.port == 8787
    assert settings.api.allow_non_loopback is False
    assert settings.api.session_https_only is False
    assert settings.alerts.adapters[0].type == "console"
    assert settings.storage.evaluation_detail_retention_days is None


def test_environment_overrides(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("REEFPROOF_TIMEZONE", "UTC")
    monkeypatch.setenv("REEFPROOF_DATA_DIRECTORY", str(tmp_path / "data"))
    monkeypatch.setenv("REEFPROOF_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("REEFPROOF_JSON_LOGS", "true")
    monkeypatch.setenv("REEFPROOF_PROJECT_ID", "legacy-reef-system")
    monkeypatch.setenv("REEFPROOF_SESSION_HTTPS_ONLY", "true")

    settings = load_settings()

    assert settings.timezone == "UTC"
    assert settings.data_directory == tmp_path / "data"
    assert settings.log_level == "DEBUG"
    assert settings.json_logs is True
    assert settings.project.project_id == "legacy-reef-system"
    assert settings.api.session_https_only is True


def test_explicit_non_loopback_api_setting_is_opt_in() -> None:
    settings = Settings(api=ApiSettings(bind="0.0.0.0", allow_non_loopback=True))

    assert settings.api.bind == "0.0.0.0"
    assert settings.api.allow_non_loopback is True


def test_local_directory_creation(tmp_path: Path) -> None:
    directory = tmp_path / "nested" / "data"
    settings = Settings(reefproof=ReefProofSettings(data_directory=directory))

    assert settings.ensure_data_directory() == directory
    assert directory.is_dir()


def test_nested_yaml_configuration_loads_without_secrets(tmp_path: Path) -> None:
    configuration = tmp_path / "reefproof.yaml"
    configuration.write_text(
        """
schema_version: "0.1"
reefproof:
  timezone: UTC
  mode: one-shot
  data_directory: ./evidence
  log_level: WARNING
  json_logs: true
hydros:
  enabled: false
  collective_selector: null
  polling_interval_seconds: 300
  maximum_config_age_seconds: 600
  request_timeout_seconds: 20
  credential_refresh_margin_seconds: 300
evaluation:
  critical_unknown_policy: alert
  evaluation_deadline_seconds: 15
alerts:
  adapters:
    - type: console
  repeat_critical_after_seconds: 3600
  send_recovery: true
api:
  bind: 127.0.0.1
  port: 8787
annotations:
  path: config/system.yaml
invariants:
  paths:
    - config/invariants
""",
        encoding="utf-8",
    )

    settings = load_settings(config_path=configuration)

    assert settings.reefproof.mode == "one-shot"
    assert settings.mode == "one-shot"
    assert settings.hydros.polling_interval_seconds == 300
    assert settings.invariants.paths == (Path("config/invariants"),)


def test_environment_overrides_nested_yaml(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configuration = tmp_path / "reefproof.yaml"
    configuration.write_text(
        'schema_version: "0.1"\nreefproof:\n  timezone: America/New_York\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("REEFPROOF_TIMEZONE", "UTC")
    monkeypatch.setenv("REEFPROOF_MODE", "watch")
    monkeypatch.setenv("REEFPROOF_API_PORT", "9999")

    settings = load_settings(config_path=configuration)

    assert settings.timezone == "UTC"
    assert settings.mode == "watch"
    assert settings.api.port == 9999


def test_yaml_rejects_secret_fields(tmp_path: Path) -> None:
    configuration = tmp_path / "reefproof.yaml"
    configuration.write_text(
        'schema_version: "0.1"\nhydros:\n  enabled: true\n  password: forbidden\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="password"):
        load_settings(config_path=configuration)


def test_yaml_rejects_duplicate_keys(tmp_path: Path) -> None:
    configuration = tmp_path / "reefproof.yaml"
    configuration.write_text(
        'schema_version: "0.1"\nreefproof:\n  mode: fixture\n  mode: watch\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate YAML key: mode"):
        load_settings(config_path=configuration)


def test_alert_adapter_types_must_be_unique() -> None:
    with pytest.raises(ValueError, match="duplicate alert adapter type: console"):
        AlertsSettings(
            adapters=(
                ConsoleAdapterSettings(),
                ConsoleAdapterSettings(),
            )
        )


def test_home_assistant_yaml_can_enable_type_but_cannot_choose_destination() -> None:
    assert HomeAssistantAdapterSettings().type == "home_assistant"
    with pytest.raises(ValueError, match="endpoint"):
        HomeAssistantAdapterSettings.model_validate(
            {
                "type": "home_assistant",
                "endpoint": "https://attacker.example/collect",
            }
        )


def test_retention_days_are_explicit_and_positive() -> None:
    assert (
        StorageSettings(evaluation_detail_retention_days=30).evaluation_detail_retention_days == 30
    )
    with pytest.raises(ValueError):
        StorageSettings(evaluation_detail_retention_days=0)


@pytest.mark.parametrize("bind", ["localhost", "127.0.0.1", "127.42.0.8", "::1"])
def test_api_bind_accepts_only_loopback_addresses(bind: str) -> None:
    assert ApiSettings(bind=bind).bind == bind


@pytest.mark.parametrize("bind", ["0.0.0.0", "::", "192.168.1.20", "reefproof.local"])
def test_api_bind_rejects_wildcard_lan_and_unresolved_hosts(bind: str) -> None:
    with pytest.raises(ValueError, match="loopback"):
        ApiSettings(bind=bind)
