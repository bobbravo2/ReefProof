import { execFile } from "node:child_process";
import { createHash } from "node:crypto";

export type CliInvocation = {
  executable: string;
  cwd: string;
  env: NodeJS.ProcessEnv;
};

export type RuntimeStatus = {
  version: string;
  operating_mode: string;
  hydros_connection: string;
  mqtt_connection: string;
  readiness: string;
  monitoring_confidence: string;
  uptime_seconds: number;
};

export type BackupResult = {
  destination: string;
  integrity: string;
  schema_version: number;
  status: string;
  latest_rule_revision: null | {
    revision_number?: number;
    provenance_label?: string;
  };
};

export function runCli(
  invocation: CliInvocation,
  args: string[],
): Promise<string> {
  return new Promise((resolve, reject) => {
    execFile(
      invocation.executable,
      args,
      { cwd: invocation.cwd, env: invocation.env, timeout: 30_000 },
      (error, stdout, stderr) => {
        if (error) {
          const detail = stderr.trim() || stdout.trim() || error.message;
          reject(new Error(detail));
          return;
        }
        resolve(stdout.trim());
      },
    );
  });
}

export function parseRuntimeStatus(value: unknown): RuntimeStatus {
  if (typeof value !== "object" || value === null) throw new Error("status response is not an object");
  const status = value as Record<string, unknown>;
  const stringFields = [
    "version",
    "operating_mode",
    "hydros_connection",
    "mqtt_connection",
    "readiness",
    "monitoring_confidence",
  ] as const;
  for (const field of stringFields) {
    if (typeof status[field] !== "string") throw new Error(`status response is missing ${field}`);
  }
  if (typeof status.uptime_seconds !== "number") throw new Error("status response is missing uptime_seconds");
  return status as RuntimeStatus;
}

export async function readRuntimeStatus(url: string): Promise<RuntimeStatus> {
  const response = await fetch(url, { redirect: "error" });
  if (!response.ok) throw new Error(`status endpoint returned ${response.status}`);
  return parseRuntimeStatus(await response.json());
}

export async function waitForRuntimeRecovery(
  url: string,
  previousUptimeSeconds: number,
  timeoutMs = 30_000,
  request: typeof fetch = fetch,
): Promise<RuntimeStatus> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await request(url, { redirect: "error" });
      if (response.ok) {
        const status = parseRuntimeStatus(await response.json());
        if (status.uptime_seconds < previousUptimeSeconds) return status;
      }
    } catch {
      // A bounded connection failure is expected while the supervisor restarts ReefProof.
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`Hosted ReefProof did not recover at ${url}`);
}

export function parseManagedDaemonPid(output: string): number {
  const match = output.match(/\bPID (\d+)\b/);
  const pidText = match?.[1];
  const pid = pidText === undefined ? Number.NaN : Number.parseInt(pidText, 10);
  if (!Number.isSafeInteger(pid) || pid <= 0) {
    throw new Error("daemon response did not contain a valid PID");
  }
  return pid;
}

export function formatStatus(buildIdentity: string, status: RuntimeStatus | undefined): string {
  const runtime = status
    ? [
        "Local workbench: ONLINE",
        `Operating mode: ${status.operating_mode}`,
        `HYDROS observation: ${status.hydros_connection}`,
        `MQTT observation: ${status.mqtt_connection}`,
        `Assurance readiness: ${status.readiness}`,
        `Monitoring confidence: ${status.monitoring_confidence}`,
        `Uptime: ${Math.floor(status.uptime_seconds)} seconds`,
      ]
    : [
        "Local workbench: OFFLINE",
        "HYDROS observation: UNKNOWN (local status unavailable)",
        "MQTT observation: UNKNOWN (local status unavailable)",
      ];
  return [...runtime, "", buildIdentity].join("\n");
}

export function parseBackupResult(output: string): BackupResult {
  const value: unknown = JSON.parse(output);
  if (typeof value !== "object" || value === null) throw new Error("backup response is not an object");
  const backup = value as Record<string, unknown>;
  if (
    typeof backup.destination !== "string" ||
    typeof backup.integrity !== "string" ||
    typeof backup.schema_version !== "number" ||
    typeof backup.status !== "string" ||
    !(backup.latest_rule_revision === null || typeof backup.latest_rule_revision === "object")
  ) {
    throw new Error("backup response is incomplete");
  }
  return backup as BackupResult;
}

export function formatBackupResult(backup: BackupResult): string {
  const revision = backup.latest_rule_revision;
  return [
    `Saved to: ${backup.destination}`,
    `Integrity: ${backup.integrity.toUpperCase()}`,
    `Schema version: ${backup.schema_version}`,
    `Latest flow revision: ${revision?.revision_number ?? "none"}`,
    `Evidence provenance: ${revision?.provenance_label ?? "none"}`,
  ].join("\n");
}

export function verifyDownloadedArtifact(
  bytes: Uint8Array,
  expectedSha256: string,
): Buffer {
  if (!/^[0-9a-f]{64}$/.test(expectedSha256)) {
    throw new Error("hosted backup digest is invalid");
  }
  const buffer = Buffer.from(bytes);
  const actualSha256 = createHash("sha256").update(buffer).digest("hex");
  if (actualSha256 !== expectedSha256) {
    throw new Error("hosted backup download digest did not match the verified artifact");
  }
  return buffer;
}
