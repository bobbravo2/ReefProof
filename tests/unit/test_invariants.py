from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from reefproof.configuration import ConfigurationFixture, load_fixture, snapshot_fixture
from reefproof.invariants import InvariantState, evaluate_graph, result_exit_code
from reefproof.reliability import build_graph

CORRELATED = Path("tests/fixtures/configuration/unsafe-correlated-returns.json")
TIMESTAMP = datetime.fromisoformat("2026-07-25T12:00:00-04:00")
RUN_ID = "12345678-1234-4234-8234-123456789abc"


def _evaluate(document: dict[str, Any] | None = None):
    fixture = (
        ConfigurationFixture.model_validate(document)
        if document is not None
        else load_fixture(CORRELATED)
    )
    return evaluate_graph(
        build_graph(snapshot_fixture(fixture)),
        evaluation_timestamp=TIMESTAMP,
        evaluation_run_id=RUN_ID,
    )


def _document() -> dict[str, Any]:
    return json.loads(CORRELATED.read_text(encoding="utf-8"))


def test_rp_circ_001_fails_for_shared_power_domain() -> None:
    run = _evaluate()
    result = run.results[0]

    assert result.invariant_id == "RP-CIRC-001"
    assert result.version == "1"
    assert result.state is InvariantState.FAIL
    assert result.severity == "critical"
    assert "share one power domain" in result.summary
    assert len(result.affected_entities) == 3
    assert len(result.evidence) == 3
    assert result.missing_evidence == ()
    assert result.configuration_hash.startswith("sha256:")
    assert result.annotation_hash.startswith("sha256:")
    assert result.policy_hash == run.policy_hash
    assert result.evaluation_run_id == RUN_ID
    assert result_exit_code(run.results) == 40


def test_rp_circ_001_passes_for_independent_power_domains() -> None:
    document = _document()
    payload = document["payload"]
    payload["authored_entities"].append(
        {
            "key": "independent-power",
            "display_name": "Example Independent Power Domain",
            "entity_type": "power_domain",
            "source": "anonymized-example",
            "owner": "example-operator",
            "last_verified": "2026-07-25",
            "review_after": "2027-01-25",
        }
    )
    payload["annotations"][2]["target_key"] = "independent-power"
    payload["annotations"].append(
        {
            "subject_key": "return-a",
            "relationship": "has_property",
            "value": {
                "dependency_map_complete": True,
                "service_mode_inventory_complete": True,
                "active_heater_inventory_complete": True,
                "active_uv_inventory_complete": True,
                "active_chiller_inventory_complete": True,
                "active_ato_inventory_complete": True,
                "automated_rodi_inventory_complete": True,
                "critical_output_inventory_complete": True,
            },
            "source": "anonymized-example",
            "owner": "example-operator",
            "last_verified": "2026-07-25",
            "review_after": "2027-01-25",
        }
    )

    run = _evaluate(document)
    result = run.results[0]

    assert result.state is InvariantState.PASS
    assert "distinct power domains" in result.summary
    assert result.missing_evidence == ()
    assert result_exit_code((result,)) == 0


def test_rp_circ_001_is_unknown_when_power_evidence_is_missing() -> None:
    document = _document()
    payload = document["payload"]
    payload["annotations"] = payload["annotations"][:2]

    run = _evaluate(document)
    result = run.results[0]

    assert result.state is InvariantState.UNKNOWN
    assert "Power domain for Return B." in result.missing_evidence
    assert result_exit_code(run.results) == 10


def test_policy_identity_is_stable() -> None:
    assert _evaluate().policy_hash == _evaluate().policy_hash
