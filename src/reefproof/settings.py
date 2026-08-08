"""Strict, human-readable ReefProof configuration."""

from __future__ import annotations

import os
from ipaddress import ip_address
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ReefProofSettings(_FrozenModel):
    timezone: str = "America/New_York"
    mode: Literal["fixture", "one-shot", "watch"] = "fixture"
    data_directory: Path = Path(".local/data")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    json_logs: bool = False

    @field_validator("timezone")
    @classmethod
    def timezone_must_exist(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError(f"unknown timezone: {value}") from error
        return value


class HydrosSettings(_FrozenModel):
    enabled: bool = False
    collective_selector: str | None = None
    polling_interval_seconds: int = Field(default=300, ge=60)
    maximum_config_age_seconds: int = Field(default=600, gt=0)
    request_timeout_seconds: int = Field(default=20, gt=0)
    credential_refresh_margin_seconds: int = Field(default=300, gt=0)


class EvaluationSettings(_FrozenModel):
    critical_unknown_policy: Literal["alert", "record"] = "alert"
    evaluation_deadline_seconds: int = Field(default=15, gt=0)


class StorageSettings(_FrozenModel):
    evaluation_detail_retention_days: int | None = Field(default=None, ge=1)
    backup_directory: Path | None = None


class ConsoleAdapterSettings(_FrozenModel):
    type: Literal["console"] = "console"


class HomeAssistantAdapterSettings(_FrozenModel):
    type: Literal["home_assistant"] = "home_assistant"


AlertAdapterSettings = ConsoleAdapterSettings | HomeAssistantAdapterSettings


class AlertsSettings(_FrozenModel):
    adapters: tuple[AlertAdapterSettings, ...] = (ConsoleAdapterSettings(),)
    repeat_critical_after_seconds: int = Field(default=3600, gt=0)
    send_recovery: bool = True

    @field_validator("adapters")
    @classmethod
    def adapters_cannot_be_empty(
        cls,
        value: tuple[AlertAdapterSettings, ...],
    ) -> tuple[AlertAdapterSettings, ...]:
        if not value:
            raise ValueError("at least one alert adapter is required")
        seen: set[str] = set()
        for adapter in value:
            if adapter.type in seen:
                raise ValueError(f"duplicate alert adapter type: {adapter.type}")
            seen.add(adapter.type)
        return value


class ApiSettings(_FrozenModel):
    allow_non_loopback: bool = False
    bind: str = "127.0.0.1"
    port: int = Field(default=8787, ge=1, le=65535)
    session_https_only: bool = False

    @field_validator("bind")
    @classmethod
    def bind_must_be_loopback_only(cls, value: str, info: ValidationInfo) -> str:
        if value == "localhost":
            return value
        try:
            address = ip_address(value)
        except ValueError as error:
            raise ValueError("api.bind must be localhost or a loopback IP address") from error
        if not address.is_loopback and not info.data.get("allow_non_loopback", False):
            raise ValueError("api.bind must be loopback-only")
        return value


class ProjectSettings(_FrozenModel):
    project_id: str = Field(default="primary-reef-system", pattern=r"^[a-z][a-z0-9_-]*$")
    display_name: str = Field(default="Primary Reef System", min_length=1)
    acceptance_authority_principal_id: str = Field(
        default="local-acceptance-authority",
        pattern=r"^[a-z][a-z0-9_-]*$",
    )
    acceptance_authority_display_name: str = Field(
        default="Local acceptance authority",
        min_length=1,
    )


class AnnotationsSettings(_FrozenModel):
    path: Path = Path("config/system.yaml")


class InvariantsSettings(_FrozenModel):
    paths: tuple[Path, ...] = (Path("config/invariants"),)


class Settings(_FrozenModel):
    """Complete v0.1 settings with Phase 0 compatibility properties."""

    schema_version: Literal["0.1"] = "0.1"
    reefproof: ReefProofSettings = ReefProofSettings()
    hydros: HydrosSettings = HydrosSettings()
    evaluation: EvaluationSettings = EvaluationSettings()
    storage: StorageSettings = StorageSettings()
    alerts: AlertsSettings = AlertsSettings()
    api: ApiSettings = ApiSettings()
    project: ProjectSettings = ProjectSettings()
    annotations: AnnotationsSettings = AnnotationsSettings()
    invariants: InvariantsSettings = InvariantsSettings()

    @model_validator(mode="before")
    @classmethod
    def accept_phase_zero_flat_fields(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        document = dict(value)
        flat_fields = {
            name: document.pop(name)
            for name in (
                "timezone",
                "data_directory",
                "log_level",
                "mode",
                "json_logs",
            )
            if name in document
        }
        if flat_fields:
            reefproof = dict(document.get("reefproof", {}))
            reefproof.update(flat_fields)
            document["reefproof"] = reefproof
        return document

    @property
    def timezone(self) -> str:
        return self.reefproof.timezone

    @property
    def data_directory(self) -> Path:
        return self.reefproof.data_directory

    @property
    def log_level(self) -> str:
        return self.reefproof.log_level

    @property
    def mode(self) -> str:
        return self.reefproof.mode

    @property
    def json_logs(self) -> bool:
        return self.reefproof.json_logs

    def ensure_data_directory(self) -> Path:
        self.data_directory.mkdir(parents=True, exist_ok=True)
        return self.data_directory


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: _UniqueKeyLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ValueError(f"duplicate YAML key: {key}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as stream:
            document = yaml.load(stream, Loader=_UniqueKeyLoader)
    except yaml.YAMLError as error:
        raise ValueError(f"invalid ReefProof YAML: {error}") from error
    if document is None:
        return {}
    if not isinstance(document, dict):
        raise ValueError("ReefProof configuration root must be a mapping")
    return document


def _apply_environment(document: dict[str, Any]) -> dict[str, Any]:
    result = {**document}
    reefproof = dict(result.get("reefproof", {}))
    api = dict(result.get("api", {}))
    storage = dict(result.get("storage", {}))
    project = dict(result.get("project", {}))
    reefproof_mapping = {
        "timezone": "REEFPROOF_TIMEZONE",
        "data_directory": "REEFPROOF_DATA_DIRECTORY",
        "log_level": "REEFPROOF_LOG_LEVEL",
        "mode": "REEFPROOF_MODE",
        "json_logs": "REEFPROOF_JSON_LOGS",
    }
    for field, variable in reefproof_mapping.items():
        if variable in os.environ:
            reefproof[field] = os.environ[variable]
    if reefproof:
        result["reefproof"] = reefproof
    if "REEFPROOF_API_BIND" in os.environ:
        api["bind"] = os.environ["REEFPROOF_API_BIND"]
    if "REEFPROOF_API_PORT" in os.environ:
        api["port"] = os.environ["REEFPROOF_API_PORT"]
    if "REEFPROOF_SESSION_HTTPS_ONLY" in os.environ:
        api["session_https_only"] = os.environ["REEFPROOF_SESSION_HTTPS_ONLY"]
    if api:
        result["api"] = api
    if "REEFPROOF_BACKUP_DIRECTORY" in os.environ:
        storage["backup_directory"] = os.environ["REEFPROOF_BACKUP_DIRECTORY"]
    if storage:
        result["storage"] = storage
    project_mapping = {
        "project_id": "REEFPROOF_PROJECT_ID",
        "display_name": "REEFPROOF_PROJECT_DISPLAY_NAME",
        "acceptance_authority_principal_id": "REEFPROOF_AUTHORITY_PRINCIPAL_ID",
        "acceptance_authority_display_name": "REEFPROOF_AUTHORITY_DISPLAY_NAME",
    }
    for field, variable in project_mapping.items():
        if variable in os.environ:
            project[field] = os.environ[variable]
    if project:
        result["project"] = project
    return result


def load_settings(
    *,
    config_path: Path | None = None,
    create_data_directory: bool = False,
) -> Settings:
    """Load strict YAML followed by explicit non-secret environment overrides."""

    selected_path = config_path
    if selected_path is None and "REEFPROOF_CONFIG_PATH" in os.environ:
        selected_path = Path(os.environ["REEFPROOF_CONFIG_PATH"])
    document = _load_yaml(selected_path) if selected_path is not None else {}
    settings = Settings.model_validate(_apply_environment(document))
    if create_data_directory:
        settings.ensure_data_directory()
    return settings
