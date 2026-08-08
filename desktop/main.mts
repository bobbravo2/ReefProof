import { access, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { app, BrowserWindow, dialog, Menu, session, shell } from "electron";

import { quitWhenParentExits } from "./lifecycle.mjs";
import { applySecurityPolicy, SECURE_WEB_PREFERENCES } from "./security.mjs";
import {
  formatBackupResult,
  formatStatus,
  parseBackupResult,
  parseManagedDaemonPid,
  readRuntimeStatus,
  runCli,
  waitForRuntimeRecovery,
  verifyDownloadedArtifact,
  type CliInvocation,
} from "./operations.mjs";
import { ownsLocalRuntime, resolveDesktopConnection } from "./connection.mjs";

const CONNECTION = resolveDesktopConnection(process.env);
const APPLICATION_ORIGIN = CONNECTION.origin;
const WORKBENCH_URL = `${APPLICATION_ORIGIN}/workbench`;
const STATUS_URL = `${APPLICATION_ORIGIN}/v1/system/status`;
const REPOSITORY_ROOT = fileURLToPath(new URL("../../", import.meta.url));
const ICON_PATH = app.isPackaged
  ? path.join(process.resourcesPath, "icon.png")
  : path.join(REPOSITORY_ROOT, "desktop", "assets", "icon.png");

// `productName` supplies this value from package.json; keep the explicit value
// for staged bundles and internal Electron metadata. The OS-visible macOS name
// comes from the packaged ReefProof.app bundle, not app.setName().
app.setName("ReefProof");
app.setAboutPanelOptions({ applicationName: "ReefProof", applicationVersion: app.getVersion() });

let stopping = false;
let startedManagedPid: number | undefined;
let mainWindow: BrowserWindow | undefined;

async function serverCommand(): Promise<{ executable: string; env: NodeJS.ProcessEnv }> {
  if (!ownsLocalRuntime(CONNECTION.mode)) {
    throw new Error("remote-hosted mode does not own a local ReefProof runtime");
  }
  if (app.isPackaged) {
    const executable = path.join(process.resourcesPath, "reefproof");
    await access(executable);
    return {
      executable,
      env: {
        ...process.env,
        REEFPROOF_ENVIRONMENT: "production",
        REEFPROOF_API_PORT: new URL(APPLICATION_ORIGIN).port || "80",
        REEFPROOF_DATA_DIRECTORY: path.join(app.getPath("userData"), "data"),
      },
    };
  }
  return {
    executable: path.join(REPOSITORY_ROOT, "reefproof"),
    env: {
      ...process.env,
      REEFPROOF_ENV: "dev",
      REEFPROOF_API_PORT: new URL(APPLICATION_ORIGIN).port || "80",
    },
  };
}

async function cliInvocation(): Promise<CliInvocation> {
  const command = await serverCommand();
  return {
    executable: command.executable,
    cwd: app.isPackaged ? process.resourcesPath : REPOSITORY_ROOT,
    env: command.env,
  };
}

async function stopServer(): Promise<void> {
  if (!ownsLocalRuntime(CONNECTION.mode)) return;
  if (stopping) return;
  stopping = true;
  if (startedManagedPid !== undefined) {
    const invocation = await cliInvocation();
    const currentPid = parseManagedDaemonPid(await runCli(invocation, ["daemon", "status"]));
    if (currentPid !== startedManagedPid) {
      throw new Error(
        `Workbench ownership changed from PID ${startedManagedPid} to PID ${currentPid}; stop was refused`,
      );
    }
    await runCli(invocation, ["daemon", "stop"]);
    startedManagedPid = undefined;
  }
}

async function startServer(): Promise<void> {
  try {
    await readRuntimeStatus(STATUS_URL);
    return;
  } catch {
    if (!ownsLocalRuntime(CONNECTION.mode)) {
      throw new Error(`Hosted ReefProof is unavailable at ${APPLICATION_ORIGIN}`);
    }
    const invocation = await cliInvocation();
    const managedAlreadyRunning = await runCli(invocation, ["daemon", "status"]).then(
      () => true,
      () => false,
    );
    if (!managedAlreadyRunning) {
      startedManagedPid = parseManagedDaemonPid(await runCli(invocation, ["daemon", "start"]));
    }
  }
  await readRuntimeStatus(STATUS_URL);
}

async function restartServer(): Promise<void> {
  if (!ownsLocalRuntime(CONNECTION.mode)) {
    const before = await readRuntimeStatus(STATUS_URL);
    await remoteOperation("/v1/operations/restart", "POST");
    await waitForRuntimeRecovery(STATUS_URL, before.uptime_seconds);
    await mainWindow?.loadURL(WORKBENCH_URL);
    return;
  }
  if (startedManagedPid === undefined) {
    throw new Error("Workbench is not owned by this Desktop session; restart was refused");
  }
  const invocation = await cliInvocation();
  const currentPid = parseManagedDaemonPid(await runCli(invocation, ["daemon", "status"]));
  if (currentPid !== startedManagedPid) {
    throw new Error(
      `Workbench ownership changed from PID ${startedManagedPid} to PID ${currentPid}; restart was refused`,
    );
  }
  startedManagedPid = parseManagedDaemonPid(await runCli(invocation, ["daemon", "restart"]));
  await mainWindow?.loadURL(WORKBENCH_URL);
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

async function remoteOperation(
  pathname: string,
  method: "GET" | "POST",
): Promise<unknown> {
  if (ownsLocalRuntime(CONNECTION.mode)) {
    throw new Error("remote operation requested in local-managed mode");
  }
  const response = await session.defaultSession.fetch(`${APPLICATION_ORIGIN}${pathname}`, {
    method,
    credentials: "include",
    redirect: "error",
    headers: { "Accept": "application/json", "X-ReefProof-Operation": "desktop" },
  });
  const document: unknown = await response.json().catch(() => undefined);
  if (!response.ok) {
    const detail = typeof document === "object" && document !== null &&
      "detail" in document && typeof document.detail === "string"
      ? document.detail : `hosted operation returned ${response.status}`;
    throw new Error(detail);
  }
  return document;
}

function hostedBackup(value: unknown): { backupId: string; sha256: string } {
  if (typeof value !== "object" || value === null ||
      !("backup_id" in value) || typeof value.backup_id !== "string" ||
      !/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(value.backup_id) ||
      !("sha256" in value) || typeof value.sha256 !== "string" ||
      !/^[0-9a-f]{64}$/.test(value.sha256)) {
    throw new Error("hosted backup response did not contain valid artifact verification");
  }
  return { backupId: value.backup_id, sha256: value.sha256 };
}

async function downloadRemoteBackup(
  backupId: string,
  expectedSha256: string,
  destination: string,
): Promise<void> {
  const response = await session.defaultSession.fetch(
    `${APPLICATION_ORIGIN}/v1/operations/backups/${encodeURIComponent(backupId)}/download`,
    {
      method: "POST",
      credentials: "include",
      redirect: "error",
      headers: { "X-ReefProof-Operation": "desktop" },
    },
  );
  if (!response.ok) throw new Error(`hosted backup download returned ${response.status}`);
  const bytes = verifyDownloadedArtifact(
    new Uint8Array(await response.arrayBuffer()),
    expectedSha256,
  );
  await writeFile(destination, bytes, { flag: "wx", mode: 0o600 });
}

async function showStatus(): Promise<void> {
  try {
    const [build, status] = await Promise.all([
      ownsLocalRuntime(CONNECTION.mode)
        ? runCli(await cliInvocation(), ["version"])
        : Promise.resolve(
            `Hosted ReefProof\nOrigin: ${APPLICATION_ORIGIN}${CONNECTION.insecureLanHttp ? "\nTransport: HTTP on private LAN" : ""}`,
          ),
      readRuntimeStatus(STATUS_URL).catch(() => undefined),
    ]);
    await dialog.showMessageBox(mainWindow!, {
      type: status ? "info" : "warning",
      title: "ReefProof Status & Build Information",
      message: status ? "ReefProof status" : "ReefProof service is offline",
      detail: formatStatus(build, status),
    });
  } catch (error) {
    await dialog.showErrorBox("ReefProof status unavailable", errorMessage(error));
  }
}

async function runDiagnostics(): Promise<void> {
  try {
    const output = ownsLocalRuntime(CONNECTION.mode)
      ? await runCli(await cliInvocation(), ["doctor"])
      : JSON.stringify(
          await remoteOperation("/v1/operations/diagnostics", "GET"),
          null,
          2,
        );
    await dialog.showMessageBox(mainWindow!, {
      type: "info",
      title: "ReefProof Diagnostics",
      message: `${CONNECTION.mode === "remote-hosted" ? "Hosted" : "Local"} diagnostics completed`,
      detail: output,
    });
  } catch (error) {
    await dialog.showErrorBox("ReefProof diagnostics failed", errorMessage(error));
  }
}

async function downloadBackup(): Promise<void> {
  if (!ownsLocalRuntime(CONNECTION.mode)) {
    try {
      const result = await remoteOperation("/v1/operations/backups", "POST");
      const backup = hostedBackup(result);
      const selected = await dialog.showSaveDialog(mainWindow!, {
        title: "Download ReefProof Hosted Backup",
        buttonLabel: "Download Backup",
        defaultPath: "reefproof-backup.sqlite3",
      });
      if (selected.canceled || !selected.filePath) return;
      await downloadRemoteBackup(backup.backupId, backup.sha256, selected.filePath);
      await dialog.showMessageBox(mainWindow!, {
        type: "info",
        title: "ReefProof Hosted Backup",
        message: "Hosted backup created and verified",
        detail: `Saved to: ${selected.filePath}\n${JSON.stringify(result, null, 2)}`,
      });
    } catch (error) {
      await dialog.showErrorBox("ReefProof hosted backup failed", errorMessage(error));
    }
    return;
  }
  const configuredRoot = process.env.REEFPROOF_BACKUP_DIRECTORY;
  const selected = await dialog.showOpenDialog(mainWindow!, {
    title: "Choose ReefProof Backup Root",
    buttonLabel: "Create Backup",
    ...(configuredRoot ? { defaultPath: configuredRoot } : {}),
    properties: ["openDirectory", "createDirectory"],
  });
  const backupRoot = selected.filePaths[0];
  if (selected.canceled || !backupRoot) return;
  try {
    const output = await runCli(await cliInvocation(), [
      "database",
      "backup",
      "--root",
      backupRoot,
    ]);
    const backup = parseBackupResult(output);
    await dialog.showMessageBox(mainWindow!, {
      type: "info",
      title: "ReefProof Backup",
      message: "Backup created and verified",
      detail: formatBackupResult(backup),
    });
  } catch (error) {
    await dialog.showErrorBox("ReefProof backup failed", errorMessage(error));
  }
}

function installApplicationMenu(): void {
  Menu.setApplicationMenu(Menu.buildFromTemplate([
    {
      label: "ReefProof",
      submenu: [
        { label: "Status & Build Information", click: () => void showStatus() },
        { type: "separator" },
        { role: "quit" },
      ],
    },
    {
      label: "Workbench",
      submenu: [
        { label: "Restart Workbench", click: () => void restartServer().catch((error) => dialog.showErrorBox("ReefProof restart failed", errorMessage(error))) },
        { label: "Run Offline Diagnostics", click: () => void runDiagnostics() },
        { type: "separator" },
        { role: "reload" },
      ],
    },
    {
      label: "Data",
      submenu: [{ label: "Download Backup…", click: () => void downloadBackup() }],
    },
    { role: "editMenu" },
    { role: "viewMenu" },
    { role: "windowMenu" },
  ]));
}

async function startDesktop(): Promise<void> {
  app.dock?.setIcon(ICON_PATH);
  session.defaultSession.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
  session.defaultSession.setPermissionCheckHandler(() => false);

  await startServer();

  mainWindow = new BrowserWindow({
    width: 1440,
    height: 1000,
    minWidth: 1024,
    minHeight: 720,
    title: `ReefProof Workbench — ${CONNECTION.mode} — ${APPLICATION_ORIGIN}${CONNECTION.insecureLanHttp ? " — HTTP LAN" : ""}`,
    icon: ICON_PATH,
    webPreferences: SECURE_WEB_PREFERENCES,
  });
  applySecurityPolicy(mainWindow.webContents, APPLICATION_ORIGIN, (url) => shell.openExternal(url));
  installApplicationMenu();
  await mainWindow.loadURL(WORKBENCH_URL);
}

app.on("window-all-closed", () => app.quit());
app.on("before-quit", (event) => {
  if (startedManagedPid !== undefined && !stopping) {
    event.preventDefault();
    void stopServer().finally(() => app.quit());
  }
});

void app.whenReady().then(startDesktop).catch(async (error: unknown) => {
  console.error(error);
  await stopServer();
  app.exit(1);
});

if (!app.isPackaged) {
  quitWhenParentExits(process.ppid, () => app.quit());
}
