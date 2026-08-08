from pathlib import Path


def test_system_status_quick_reference_uses_current_api_contract() -> None:
    reference = Path("SYSTEM_STATUS_QUICK_REF.md").read_text(encoding="utf-8")

    for canonical in (
        "`GET /v1/system/status`",
        "`GET /v1/system/health/live`",
        "`GET /v1/system/health/ready`",
        "`GET /v1/system/metrics`",
        "`GET /v1/findings`",
        "`bootstrap_secret`",
        "`claim_backup()`",
    ):
        assert canonical in reference
    for retired in (
        "`GET /v1/workbench/system-status`",
        "### GET /status",
        "### GET /health/live",
        "### GET /health/ready",
        "operator_token",
        "claim_backup_artifact",
        "## Missing Implementation",
    ):
        assert retired not in reference


def test_target_lxc_validation_uses_versioned_system_routes() -> None:
    runbook = Path("docs/v0.1-lxc-deployment-validation.md").read_text(encoding="utf-8")

    assert "http://PRIVATE_LXC_IP:8787/v1/system/health/live" in runbook
    assert "http://PRIVATE_LXC_IP:8787/v1/system/status" in runbook
    assert "http://PRIVATE_LXC_IP:8787/status" not in runbook


def test_public_release_documents_and_accepted_api_decision_are_current() -> None:
    adr = Path("docs/adr/0008-versioned-api-and-terminology-contract.md").read_text(
        encoding="utf-8"
    )
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "- Status: Accepted" in adr
    assert "awaiting Customer 0 acceptance" not in adr
    for required in (
        Path("LICENSE"),
        Path("CONTRIBUTING.md"),
        Path("SECURITY.md"),
        Path("CODE_OF_CONDUCT.md"),
        Path("docs/open-source-release-checklist.md"),
    ):
        assert required.is_file()
        assert required.name in readme
