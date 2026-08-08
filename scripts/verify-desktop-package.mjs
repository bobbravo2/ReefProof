import { execFileSync } from "node:child_process";
import { constants } from "node:fs";
import { access, lstat, readFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  assertNoPrivateRuntimeState,
  collectTreePaths,
  readBuildDate,
  readProjectVersion,
  readSourceRevision,
  verifyBinaryIdentity,
} from "./package-desktop.mjs";

const repositoryRoot = fileURLToPath(new URL("../", import.meta.url));
const version = await readProjectVersion(repositoryRoot);
const revision = readSourceRevision(repositoryRoot);
const appRoot = path.join(
  repositoryRoot,
  "dist",
  "desktop",
  `ReefProof-darwin-${process.arch}`,
  "ReefProof.app",
);
const contents = path.join(appRoot, "Contents");
const resources = path.join(contents, "Resources");
const plist = path.join(contents, "Info.plist");

await Promise.all([
  access(path.join(contents, "MacOS", "ReefProof"), constants.X_OK),
  access(path.join(resources, "app.asar")),
  access(path.join(resources, "reefproof"), constants.X_OK),
  access(path.join(resources, "icon.png")),
  access(path.join(resources, "electron.icns")),
]);
await assertNoPrivateRuntimeState(resources);

const binaryVersion = execFileSync(path.join(resources, "reefproof"), ["version"], {
  encoding: "utf8",
});
verifyBinaryIdentity(binaryVersion, version, revision);

for (const key of ["CFBundleShortVersionString", "CFBundleVersion"]) {
  const actual = execFileSync("/usr/libexec/PlistBuddy", ["-c", `Print :${key}`, plist], {
    encoding: "utf8",
  }).trim();
  if (actual !== version) throw new Error(`${key} is ${actual}; expected ${version}`);
}

const digest = async (file) => createHash("sha256").update(await readFile(file)).digest("hex");
const sourceIconDigest = await digest(path.join(repositoryRoot, "desktop", "assets", "icon.icns"));
const packagedIconDigest = await digest(path.join(resources, "electron.icns"));
if (sourceIconDigest !== packagedIconDigest) throw new Error("packaged macOS icon does not match source");

const expectedTimestamp = readBuildDate(repositoryRoot).getTime();
for (const entry of await collectTreePaths(appRoot)) {
  const actualTimestamp = (await lstat(entry)).mtimeMs;
  if (Math.abs(actualTimestamp - expectedTimestamp) > 1_000) {
    throw new Error(`packaged timestamp drift: ${entry}`);
  }
}

process.stdout.write(`PASS: verified unsigned ReefProof ${version} macOS app: ${appRoot}\n`);
