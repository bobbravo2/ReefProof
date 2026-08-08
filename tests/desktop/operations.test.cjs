const assert = require("node:assert/strict");
const test = require("node:test");

test("desktop status keeps local and observed transport states distinct", async () => {
  const { formatStatus, parseRuntimeStatus } = await import("../../.build/desktop/operations.mjs");
  const status = parseRuntimeStatus({
    version: "0.1.0",
    operating_mode: "fixture",
    hydros_connection: "offline",
    mqtt_connection: "disabled",
    readiness: "degraded",
    monitoring_confidence: "degraded",
    uptime_seconds: 12.9,
  });

  assert.equal(formatStatus("ReefProof 0.1.0\nGit commit: abc123", status), [
    "Local workbench: ONLINE",
    "Operating mode: fixture",
    "HYDROS observation: offline",
    "MQTT observation: disabled",
    "Assurance readiness: degraded",
    "Monitoring confidence: degraded",
    "Uptime: 12 seconds",
    "",
    "ReefProof 0.1.0",
    "Git commit: abc123",
  ].join("\n"));
});

test("desktop offline status does not imply transport reachability", async () => {
  const { formatStatus } = await import("../../.build/desktop/operations.mjs");
  const output = formatStatus("ReefProof 0.1.0", undefined);
  assert.match(output, /Local workbench: OFFLINE/);
  assert.match(output, /HYDROS observation: UNKNOWN \(local status unavailable\)/);
  assert.match(output, /MQTT observation: UNKNOWN \(local status unavailable\)/);
});

test("desktop rejects incomplete ReefProof status documents", async () => {
  const { parseRuntimeStatus } = await import("../../.build/desktop/operations.mjs");
  assert.throws(() => parseRuntimeStatus({ version: "0.1.0" }), /operating_mode/);
});

test("desktop extracts and validates managed daemon ownership", async () => {
  const { parseManagedDaemonPid } = await import("../../.build/desktop/operations.mjs");
  assert.equal(parseManagedDaemonPid("Started ReefProof daemon (PID 4321)."), 4321);
  assert.equal(parseManagedDaemonPid("ReefProof daemon is running (PID 9876)."), 9876);
  assert.throws(() => parseManagedDaemonPid("ReefProof daemon is stopped."), /valid PID/);
});

test("desktop backup result is concise and preserves verification metadata", async () => {
  const { formatBackupResult, parseBackupResult } = await import("../../.build/desktop/operations.mjs");
  const backup = parseBackupResult(JSON.stringify({
    destination: "/Documents/reefproof-backup.sqlite3",
    integrity: "ok",
    schema_version: 7,
    status: "PASS",
    latest_rule_revision: { revision_number: 2, provenance_label: "MANUAL / NOT LIVE" },
    source: ".local/data/reefproof.sqlite3",
  }));

  assert.equal(formatBackupResult(backup), [
    "Saved to: /Documents/reefproof-backup.sqlite3",
    "Integrity: OK",
    "Schema version: 7",
    "Latest flow revision: 2",
    "Evidence provenance: MANUAL / NOT LIVE",
  ].join("\n"));
});

test("desktop restart waits for a new hosted runtime", async () => {
  const { waitForRuntimeRecovery } = await import("../../.build/desktop/operations.mjs");
  const uptimes = [120, 121, 0.2];
  const request = async () => ({
    ok: true,
    async json() {
      return {
        version: "0.1.0",
        operating_mode: "fixture",
        hydros_connection: "disabled",
        mqtt_connection: "disabled",
        readiness: "unready",
        monitoring_confidence: "unknown",
        uptime_seconds: uptimes.shift(),
      };
    },
  });
  const recovered = await waitForRuntimeRecovery(
    "http://192.168.1.20:8787/v1/system/status",
    120,
    1_000,
    request,
  );
  assert.equal(recovered.uptime_seconds, 0.2);
});

test("desktop verifies hosted backup bytes before writing", async () => {
  const { verifyDownloadedArtifact } = await import("../../.build/desktop/operations.mjs");
  const bytes = Buffer.from("verified backup fixture");
  const digest = require("node:crypto").createHash("sha256").update(bytes).digest("hex");
  assert.deepEqual(verifyDownloadedArtifact(bytes, digest), bytes);
  assert.throws(
    () => verifyDownloadedArtifact(bytes, "0".repeat(64)),
    /did not match/,
  );
});
