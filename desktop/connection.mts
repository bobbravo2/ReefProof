import { isIP } from "node:net";

export type DesktopMode = "local-managed" | "remote-hosted";

export type DesktopConnection = Readonly<{
  mode: DesktopMode;
  origin: string;
  insecureLanHttp: boolean;
}>;

function privateAddress(hostname: string): boolean {
  if (isIP(hostname) === 4) {
    const [first = -1, second = -1] = hostname.split(".").map(Number);
    return first === 10 || (first === 172 && second >= 16 && second <= 31) ||
      (first === 192 && second === 168);
  }
  if (isIP(hostname) === 6) {
    const first = Number.parseInt(hostname.split(":", 1)[0] ?? "", 16);
    return Number.isFinite(first) && (first & 0xfe00) === 0xfc00;
  }
  return false;
}
function remoteOrigin(value: string | undefined): URL {
  if (!value) throw new Error("remote ReefProof origin is required");
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new Error("remote ReefProof origin must be an absolute HTTP URL");
  }
  if ((url.protocol !== "http:" && url.protocol !== "https:") ||
      url.username || url.password || url.search || url.hash || url.pathname !== "/" ||
      !privateAddress(url.hostname)) {
    throw new Error("remote ReefProof origin must be a private-LAN IP origin without credentials, path, query, or fragment");
  }
  return url;
}

export function resolveDesktopConnection(env: NodeJS.ProcessEnv): DesktopConnection {
  const mode = env.REEFPROOF_DESKTOP_MODE ?? "local-managed";
  if (mode === "local-managed") {
    if (env.REEFPROOF_REMOTE_ORIGIN) {
      throw new Error("remote ReefProof origin is not allowed in local-managed mode");
    }
    const port = env.REEFPROOF_API_PORT ?? "8787";
    if (!/^\d+$/.test(port) || Number(port) < 1 || Number(port) > 65535) {
      throw new Error("local ReefProof port must be between 1 and 65535");
    }
    return Object.freeze({
      mode,
      origin: `http://127.0.0.1:${port}`,
      insecureLanHttp: false,
    });
  }
  if (mode !== "remote-hosted") {
    throw new Error("REEFPROOF_DESKTOP_MODE must be local-managed or remote-hosted");
  }
  const url = remoteOrigin(env.REEFPROOF_REMOTE_ORIGIN);
  return Object.freeze({
    mode,
    origin: url.origin,
    insecureLanHttp: url.protocol === "http:",
  });
}

export function ownsLocalRuntime(mode: DesktopMode): boolean {
  return mode === "local-managed";
}
