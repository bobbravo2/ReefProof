from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECK = REPO_ROOT / "scripts" / "check-runtime-authority.py"


def run_check(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECK), "--root", str(root)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_offline_hydros_modules_and_fixtures_are_not_transport_capability(tmp_path: Path) -> None:
    source = tmp_path / "src" / "reefproof"
    source.mkdir(parents=True)
    (source / "hydros.py").write_text(
        "from pathlib import Path\n\ndef load_hydros_export(path: Path) -> bytes:\n"
        "    return path.read_bytes()\n",
        encoding="utf-8",
    )

    result = run_check(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "no MQTT client or vendor transport import" in result.stdout


def test_vendor_transport_client_import_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "src" / "reefproof"
    source.mkdir(parents=True)
    (source / "transport.py").write_text("import paho.mqtt.client\n", encoding="utf-8")

    result = run_check(tmp_path)

    assert result.returncode == 1
    assert "forbidden transport import" in result.stdout
    assert "paho" in result.stdout


def test_mqtt_runtime_module_is_rejected_without_a_client_dependency(tmp_path: Path) -> None:
    source = tmp_path / "src" / "reefproof"
    source.mkdir(parents=True)
    (source / "mqtt_bridge.py").write_text("def publish(): pass\n", encoding="utf-8")

    result = run_check(tmp_path)

    assert result.returncode == 1
    assert "MQTT-named runtime module" in result.stdout
