import type { ChildProcess } from "node:child_process";
import { createServer, type Server } from "node:net";

const EXIT_TIMEOUT_MS = 5_000;

export function quitWhenParentExits(
  parentPid: number,
  quit: () => void,
  intervalMs = 500,
  processIsAlive: (pid: number) => boolean = (pid) => {
    try {
      process.kill(pid, 0);
      return true;
    } catch {
      return false;
    }
  },
): NodeJS.Timeout {
  const watcher = setInterval(() => {
    if (!processIsAlive(parentPid)) {
      clearInterval(watcher);
      quit();
    }
  }, intervalMs);
  watcher.unref();
  return watcher;
}

export async function assertLoopbackPortAvailable(
  host: string,
  port: number,
  createProbe: () => Server = createServer,
): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    const probe = createProbe();
    probe.unref();
    probe.once("error", reject);
    probe.listen(port, host, () => probe.close((error) => error ? reject(error) : resolve()));
  });
}

function exited(child: ChildProcess): Promise<void> {
  if (child.exitCode !== null || child.signalCode !== null) return Promise.resolve();
  return new Promise((resolve) => child.once("exit", () => resolve()));
}

export async function terminateChild(
  child: ChildProcess | undefined,
  timeoutMs = EXIT_TIMEOUT_MS,
): Promise<void> {
  if (!child || child.exitCode !== null || child.signalCode !== null) return;
  child.kill("SIGTERM");
  const timeout = new Promise<"timeout">((resolve) => {
    const timer = setTimeout(() => resolve("timeout"), timeoutMs);
    timer.unref();
  });
  if ((await Promise.race([exited(child).then(() => "exit" as const), timeout])) === "timeout") {
    child.kill("SIGKILL");
    await exited(child);
  }
}

export async function waitUntilReachable(
  url: string,
  child: ChildProcess,
  timeoutMs = 30_000,
): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (child.exitCode !== null || child.signalCode !== null) {
      throw new Error(`ReefProof server exited before ${url} became reachable`);
    }
    try {
      const response = await fetch(url, { redirect: "error" });
      if (response.ok) return;
    } catch {
      // Startup connection failures are expected until the listener is ready.
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`Timed out waiting for ${url}`);
}
