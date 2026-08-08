import { execFileSync } from "node:child_process";
import { constants } from "node:fs";
import {
  access,
  copyFile,
  lstat,
  lutimes,
  mkdir,
  readFile,
  readdir,
  rm,
  utimes,
  writeFile,
} from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { packager } from "@electron/packager";

const REPOSITORY_ROOT = fileURLToPath(new URL("../", import.meta.url));

export async function readProjectVersion(repositoryRoot) {
  const pyproject = await readFile(path.join(repositoryRoot, "pyproject.toml"), "utf8");
  const match = /^version = "(\d+\.\d+\.\d+)"$/m.exec(pyproject);
  if (!match) throw new Error("pyproject.toml must define a numeric project version");
  return match[1];
}

export function readSourceRevision(repositoryRoot) {
  return execFileSync("git", ["rev-parse", "HEAD"], {
    cwd: repositoryRoot,
    encoding: "utf8",
  }).trim();
}

export function verifyBinaryIdentity(output, version, revision) {
  if (!output.startsWith(`ReefProof ${version}\n`)) {
    throw new Error(`desktop binary does not match project version ${version}`);
  }
  if (!output.includes(`Git commit: ${revision}`)) {
    throw new Error(`desktop binary does not match Git revision ${revision}`);
  }
}

export async function createDesktopStage(repositoryRoot, stageRoot, version) {
  const compiledRoot = path.join(repositoryRoot, ".build", "desktop");
  const compiledFiles = (await readdir(compiledRoot)).filter((name) => name.endsWith(".mjs"));
  if (!compiledFiles.includes("main.mjs")) throw new Error("desktop main process is not compiled");

  await rm(stageRoot, { recursive: true, force: true });
  await mkdir(stageRoot, { recursive: true });
  await Promise.all(
    compiledFiles.map((name) => copyFile(path.join(compiledRoot, name), path.join(stageRoot, name))),
  );
  await writeFile(
    path.join(stageRoot, "package.json"),
    `${JSON.stringify({ name: "reefproof-desktop", productName: "ReefProof", version, main: "main.mjs", private: true }, null, 2)}\n`,
  );
}

export function readBuildDate(repositoryRoot) {
  const sourceDateEpoch = process.env.SOURCE_DATE_EPOCH;
  const timestamp = sourceDateEpoch
    ? Number.parseInt(sourceDateEpoch, 10)
    : Number.parseInt(
        execFileSync("git", ["show", "-s", "--format=%ct", "HEAD"], {
          cwd: repositoryRoot,
          encoding: "utf8",
        }).trim(),
        10,
      );
  if (!Number.isSafeInteger(timestamp) || timestamp <= 0) {
    throw new Error("build timestamp must be a positive Unix epoch value");
  }
  return new Date(timestamp * 1000);
}

export async function collectTreePaths(root) {
  const paths = [];
  async function visit(current) {
    const metadata = await lstat(current);
    if (metadata.isDirectory() && !metadata.isSymbolicLink()) {
      for (const entry of await readdir(current)) await visit(path.join(current, entry));
    }
    paths.push(current);
  }
  await visit(root);
  return paths;
}

export async function assertNoPrivateRuntimeState(root) {
  const forbiddenNames = new Set([".local", "operator-totp.json"]);
  const forbiddenSuffixes = [".sqlite", ".sqlite3", ".db", ".log", ".snapshot.json"];
  for (const entry of await collectTreePaths(root)) {
    const relative = path.relative(root, entry);
    const components = relative.split(path.sep);
    const basename = path.basename(entry).toLowerCase();
    if (components.some((component) => forbiddenNames.has(component.toLowerCase())) ||
        forbiddenSuffixes.some((suffix) => basename.endsWith(suffix))) {
      throw new Error(`packaged private runtime state is forbidden: ${relative}`);
    }
  }
}

export async function normalizeTreeTimestamps(root, buildDate) {
  for (const entry of await collectTreePaths(root)) {
    const metadata = await lstat(entry);
    if (metadata.isSymbolicLink()) await lutimes(entry, buildDate, buildDate);
    else await utimes(entry, buildDate, buildDate);
  }
}

export async function packageDesktop(repositoryRoot = REPOSITORY_ROOT) {
  if (process.platform !== "darwin") throw new Error("desktop packaging is macOS-first in this slice");

  const version = await readProjectVersion(repositoryRoot);
  const revision = readSourceRevision(repositoryRoot);
  const runtimeRoot = path.join(repositoryRoot, ".build", "desktop-runtime");
  const binary = path.join(runtimeRoot, "reefproof");
  const stagedRevision = (await readFile(path.join(runtimeRoot, "revision"), "utf8")).trim();
  const pngIcon = path.join(repositoryRoot, "desktop", "assets", "icon.png");
  const macIcon = path.join(repositoryRoot, "desktop", "assets", "icon.icns");
  await Promise.all([access(binary, constants.X_OK), access(pngIcon), access(macIcon)]);

  if (stagedRevision !== revision) {
    throw new Error(`staged desktop binary is ${stagedRevision}; expected ${revision}`);
  }

  const binaryVersion = execFileSync(binary, ["version"], { encoding: "utf8" });
  verifyBinaryIdentity(binaryVersion, version, revision);

  const stageRoot = path.join(repositoryRoot, ".build", "desktop-package");
  const outputRoot = path.join(repositoryRoot, "dist", "desktop");
  await createDesktopStage(repositoryRoot, stageRoot, version);
  const appPaths = await packager({
    dir: stageRoot,
    name: "ReefProof",
    platform: "darwin",
    arch: process.arch,
    out: outputRoot,
    overwrite: true,
    asar: true,
    prune: false,
    appBundleId: "org.reefproof.desktop",
    appVersion: version,
    buildVersion: version,
    icon: macIcon,
    extraResource: [binary, pngIcon],
    quiet: true,
  });
  if (appPaths.length !== 1) throw new Error(`expected one macOS app, received ${appPaths.length}`);
  const appBundle = path.join(appPaths[0], "ReefProof.app");
  await normalizeTreeTimestamps(appBundle, readBuildDate(repositoryRoot));
  process.stdout.write(`PASS: packaged ReefProof ${version}: ${appBundle}\n`);
  return appBundle;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  packageDesktop().catch((error) => {
    console.error(`FAIL: ${error instanceof Error ? error.message : String(error)}`);
    process.exitCode = 1;
  });
}
