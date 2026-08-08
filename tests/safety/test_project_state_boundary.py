from __future__ import annotations

import ast
from pathlib import Path

DOMAIN_MODULES = (
    Path("src/reefproof/project_state.py"),
    Path("src/reefproof/recommendations.py"),
    Path("src/reefproof/information_architecture.py"),
    Path("src/reefproof/trust.py"),
)

FORBIDDEN_IMPORT_PREFIXES = (
    "reefproof.alerting",
    "reefproof.api",
    "reefproof.hydros",
    "reefproof.service",
    "httpx",
    "requests",
)


def test_project_state_foundation_has_no_transport_or_controller_capability() -> None:
    for path in DOMAIN_MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported.append(node.module)

        assert not any(
            module.startswith(prefix) for module in imported for prefix in FORBIDDEN_IMPORT_PREFIXES
        ), (path, imported)


def test_domain_foundation_contains_no_llm_or_generic_chat_contract() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in DOMAIN_MODULES)

    for forbidden in (
        "openai",
        "anthropic",
        "chat_completion",
        "mqtt",
        "publish(",
        "set_output",
        "update_firmware",
    ):
        assert forbidden not in source.casefold()


def test_trust_slice_has_no_controller_mutation_or_secret_response_contract() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            Path("src/reefproof/trust.py"),
            Path("src/reefproof/auth_totp.py"),
            Path("src/reefproof/api/projects.py"),
        )
    ).casefold()
    for forbidden in (
        "mqtt",
        "publish(",
        "set_output",
        "update_firmware",
        'provisioning_uri":',
        'totp_code": code',
    ):
        assert forbidden not in source
